import datetime
import json
import xml.etree.ElementTree
import xml.sax.saxutils
import zipfile
import logging
import base64
import copy
import uuid

import requests

logging.basicConfig(
    format=(
        "{'time':'%(asctime)s', 'name': '%(name)s',"
        "'level': '%(levelname)s', 'message': '%(message)s'}"
    ),
    level='INFO',
)
log = logging.getLogger(__file__)


def read_google_hangouts_message_data(google_takeout_zip_file):
    """ Read the zip file [Google Takeout](https://takeout.google.com/)
    generates and extract the `Takeout/Hangouts/Hangouts.json` data
    """
    hangouts_data_fp = 'Takeout/Hangouts/Hangouts.json'
    log.info(
        f'Reading {hangouts_data_fp} from "{google_takeout_zip_file}" archive'
    )

    with zipfile.ZipFile(google_takeout_zip_file) as zf:
        f = zf.open(hangouts_data_fp)
        data = json.load(f)
        return data


def validate_keys(d, keys):
    """ Validate dictionary d has exactly keys
    """
    check_keys = set(keys)
    has_keys = set(d.keys())

    missing_keys = check_keys - has_keys
    if len(missing_keys):
        raise ValueError(f'Dict missing keys {missing_keys} has {has_keys}')

    extra_keys = has_keys - check_keys
    if len(extra_keys):
        raise ValueError(f'Dict extra keys {extra_keys} not only {check_keys}')


def parsed_hangouts_conversation_meta(conversation):
    """ Extract the meta data about the conversation including participants

    """
    # conversation.conversation
    convo = conversation['conversation']['conversation']

    # check if we know about all the keys
    validate_keys(
        convo,
        [
            'current_participant',
            'force_history_state',
            'fork_on_external_invite',
            'group_link_sharing_status',
            'has_active_hangout',
            'id',
            'network_type',
            'otr_status',
            'otr_toggle',
            'participant_data',
            'read_state',
            'self_conversation_state',
            'type'
        ]
    )

    # conversation.id
    conversation_id = convo['id']

    # conversation.type
    # values: STICKY_ONE_TO_ONE, GROUP
    if convo['type'] == 'STICKY_ONE_TO_ONE':
        conversation_type = 'one_to_one'
    elif convo['type'] == 'GROUP':
        conversation_type = 'group'
    else:
        raise ValueError(
            f"unknown conversation type {convo['type']}"
        )

    # conversation.self_conversation_state
    self_conversation_state = convo['self_conversation_state']
    user_gaia_id = (
        self_conversation_state['self_read_state']['participant_id']['gaia_id']
    )

    # conversation.read_state
    # convo['read_state']

    # conversation.has_active_hangout
    # convo['has_active_hangout']

    # conversation.otr_status
    # convo['otr_status']

    # conversation.otr_toggle
    # convo['otr_toggle']

    # conversation.fork_on_external_invite
    # convo['fork_on_external_invite']

    # conversation.network_type
    # convo['network_type']

    # conversation.force_history_state
    # convo['force_history_state']

    # conversation.group_link_sharing_status
    # convo['group_link_sharing_status']

    # conversation.current_participant
    # summary of participant data
    # convo['current_participant']

    # conversation.participant_data
    user = None
    participants = []
    for participant in convo['participant_data']:

        # participant.participant_type
        # values: OFF_NETWORK_PHONE, GAIA, UNKNOWN_PHONE_NUMBER, MALFORMED_PHONE_NUMBER  # noqa
        participant_type = participant['participant_type']

        gaia_id = participant['id']['gaia_id']

        if gaia_id == user_gaia_id:
            user = {
                'gaia_id': gaia_id,
                'phone_number': participant['fallback_name'],
            }
            continue
        elif participant_type == 'GAIA':
            if 'phone_number' not in participant:
                phone_number = ''
            else:
                phone_number = participant['phone_number']['e164']
        elif participant_type == 'OFF_NETWORK_PHONE':
            phone_number = participant['phone_number']['e164']
        elif participant_type == 'UNKNOWN_PHONE_NUMBER':
            # These appear to be anonymous phone numbers. In my sample I only
            # had 1 and it was a VOICEMAIL which was unimportant
            log.warning(
                'Participant with UNKNOWN_PHONE_NUMBER, currently ignoring these messages'  # noqa
            )
            continue
        elif participant_type == 'MALFORMED_PHONE_NUMBER':
            # These appear to be from organizations, e.g. Chase Bank sends a
            # notification to 88888 number which google says is "malformed"
            phone_number = participant['fallback_name']
        else:
            raise NotImplementedError(
                f'unknown participant type {participant_type}'
            )
        participants.append({
            'gaia_id': gaia_id,
            'phone_number': phone_number,
        })

    if user is None:
        raise ValueError('Wait! Where is the user?')
    if conversation_type == 'STICKY_ONE_TO_ONE' and len(participants) != 1:
        raise ValueError(
            f'Should be a 1-1 not {len(participants)} participants'
        )

    return {
        'conversation_id': conversation_id,
        'conversation_type': conversation_type,
        'events_count': len(conversation['events']),
        'user': user,
        'participants': participants,
        'participants_count': len(participants),
    }


def parse_hangouts_event(event):
    """ Parse relevant information from the Google Hangouts JSON

    """
    # check if we know about all the keys
    validate_keys(
        event,
        [
            'conversation_id',
            'sender_id',
            'timestamp',
            'self_event_state',
            'chat_message',
            'event_id',
            'advances_sort_timestamp',
            'event_otr',
            'delivery_medium',
            'event_type',
            'event_version',
        ]
    )

    # collect relevant information for sms or mms
    parsed = {
        'parts': []
    }

    # conversation_id
    # conversation_id.id matches parent
    parsed['conversation_id'] = event['conversation_id']['id']

    # sender_id
    # keys: gaia_id, chat_id
    parsed['sender_gaia_id'] = event['sender_id']['gaia_id']

    # example: '1576525471673269' probably unix
    # timestamp / 1000 / 1000 in nanosec
    parsed['timestamp'] = datetime.datetime.fromtimestamp(
        int(event['timestamp']) / 1000 / 1000
    )
    # int(dt.timestamp() * 1000)

    # keys: 'notification_level', 'user_id.gaia_id', 'user_id.chat_id'
    # event['self_event_state']
    parsed['user_gaia_id'] = (
        event['self_event_state']['user_id']['gaia_id']
    )

    # event_id
    # example: '8QLSTrym2cg92booEdZ5wx'
    parsed['event_id'] = event['event_id']

    # advances_sort_timestamp
    # type: bool
    # event['advances_sort_timestamp']

    # event_otr
    # type: str
    # values: ON_THE_RECORD
    # event['event_otr']

    # delivery_medium.medium_type
    # values: GOOGLE_VOICE_MEDIUM, BABEL_MEDIUM, UNKNOWN_MEDIUM'
    # event['delivery_medium']

    # event_version
    # example: '1576525471673269'
    # event['event_version']

    # event_type
    # type: str
    # values: SMS, REGULAR_CHAT_MESSAGE, VOICEMAIL
    event_type = event['event_type']

    # chat_message
    # keys: message_content, annotation
    chat_message = event['chat_message']

    # chat_message.message_content
    # keys: segment, attachment
    message_content = chat_message['message_content']

    # chat_message.message_content.segment
    # keys: formatting, link_data, text, type
    # multiple lengths, sometimes not present
    segments = message_content.get('segment')

    if segments is not None:
        text = ''
        for segment in segments:
            # segment.type
            # {'TEXT': 42488, 'LINE_BREAK': 7899, 'LINK': 1531}
            segment_type = segment['type']

            # segment.text
            # optional, often present
            segment_text = segment.get('text', '')

            # segment.formatting
            # optional, sometimes empty dict
            # keys: bold, italics, strikethrough, underline
            # segment_formatting = segment.get('formatting')

            # segment.link_data
            # description: appears to be just for hangouts to provide custom
            #   link location.
            # keys: link_target, display_url
            # segment_link_data = segment.get('link_data')
            # if segment_link_data is not None:
            #     # segment.link_data.link_target
            #     segment_link_target = segment_link_data['link_target']
            #
            #     # segment.link_data.display_url
            #     # optional
            #     segment_link_url = segment_link_data.get('display_url')

            if segment_type == 'LINE_BREAK':
                text += '\n'
            elif segment_type == 'TEXT':
                text += segment_text
            elif segment_type == 'LINK':
                # links are stored separately in google hangouts but
                # are really just part of the message (or whole message)
                # so I'm making them part of it with spaces
                text += f' {segment_text} '
            else:
                raise ValueError(f'unknown segment type {segment_type}')
        parsed['parts'].append({
            'content_type': 'text/plain',
            'text': text,
        })

    # chat_message.attachment
    # required: false
    # type: list
    # keys: embed_item, id
    attachments = message_content.get('attachment', [])
    if len(attachments):
        # my sample only ever had 1 attachment
        if len(attachments) > 1:
            raise NotImplementedError(
                f'Determine handling of {len(attachments)} attachments'
            )

        attachment = attachments[0]

        # attachment.id
        # required: true
        # attachment_id = attachment['id']

        # attachment.embed_item
        # required: true
        attachment_embed_item = attachment['embed_item']

        # attachment.embed_item.type
        # values: ['PLUS_AUDIO_V2'], ['PLUS_PHOTO'], ['PLACE_V2', 'THING_V2', 'THING'] # noqa
        attachment_embed_item_type = attachment_embed_item['type']

        if attachment_embed_item_type == ['PLUS_PHOTO']:
            # the Google Takeout export does send the photos but there's not
            # a simple mapping between the json data and those image filenames.
            # Some of the json data fields have different file format than the
            # files available (jpg vs png).
            url = attachment_embed_item['plus_photo']['url']

            log.info(f'downloading image')

            resp = requests.get(url)
            content_type = resp.headers['Content-Type']
            options = ['image/jpeg', 'image/png', 'image/gif']
            # 'text/plain'
            if content_type not in options:
                raise ValueError(
                    f'unknown content type {content_type} not in {options}'
                )
            image_data = base64.b64encode(resp.content).decode('ascii')
            parsed['parts'].append({
                'content_type': content_type,
                'data': image_data,
            })
        elif attachment_embed_item_type == ['PLACE_V2', 'THING_V2', 'THING']:
            # This appears to be for maps data but I can ignore,
            # just a regular link
            pass
        elif attachment_embed_item_type == ['PLUS_AUDIO_V2']:
            # All of these appear to be VOICEMAIL with associated text.
            # Let's confirm.
            if event_type != 'VOICEMAIL':
                raise ValueError(
                    f'Unknown event type for PLUS_AUDIO_V2 called {event_type}'
                )

            log.warning('No processing PLUS_AUDIO_V2')
        else:
            raise NotImplementedError(
                f'You need to handle embed item '
                f'type = {attachment_embed_item_type}'
            )

    # chat_message.annotation
    # required: false
    # type: list
    # keys: type, value
    annotations = chat_message.get('annotation', [])
    if len(annotations):
        # my sample only ever had 1 annotations
        if len(annotations) > 1:
            raise NotImplementedError(
                f'Determine handling of {len(annotations)} annotations'
            )

        annotation = annotations[0]

        # annotation.type
        # type: int
        # description:
        # annotation_type = annotation['type']

        # annotation.value
        # type: str
        # description: all values I had were empty string
        annotation_value = annotation['value']

        if annotation_value != '':
            raise NotImplementedError(
                f'Oh! You found a non-empty annotation "{annotation_value}". '
                f'Please figure out how to handle this.'
            )

    return parsed


def xml_escape_text(text):
    """ Escape xml text for SMS Backup & Restore
    """
    additional_escapes = {
        '\n': '&#10;'
    }
    return xml.sax.saxutils.escape(text, additional_escapes)


def transform_parsed_hangouts_event_to_sms_backup_and_restore(parsed_hangouts_event, conversation_meta):  # noqa
    """ Transform the parsed hangouts data into XML elements to
    be used by SMS Backup & Restore.

    Parameters:
        parsed_hangouts_event (dict): The parsed event object returned
            by parse_hangouts_event(...) function
        conversation_meta (dict): The parsed conversation data returned
            by parsed_hangouts_conversation_meta(...) function

    Returns:
        list[Element] : list of sms or mms tagged XML elements for
            SMS Backup & Restore

    """
    date = str(int(parsed_hangouts_event['timestamp'].timestamp() * 1000))

    sender_gaia_id = parsed_hangouts_event['sender_gaia_id']
    if sender_gaia_id == parsed_hangouts_event['user_gaia_id']:
        sent_type = 2  # Sent
    else:
        sent_type = 1  # Received

    if len(parsed_hangouts_event['parts']) == 0:
        log.warning(
            'NO PARTS FOR MESSAGE '
            'event_id={event_id} conversation_id={conversation_id}'
            .format(**parsed_hangouts_event)
        )
        return []

    is_sms = (
        True
        & (len(parsed_hangouts_event['parts']) == 1)
        & (parsed_hangouts_event['parts'][0]['content_type'] == 'text/plain')
        & (conversation_meta['participants_count'] == 1)
    )
    if is_sms:
        phone_address = conversation_meta['participants'][0]['phone_number']

        element_sms = xml.etree.ElementTree.Element('sms')
        element_sms.attrib = {
            'protocol': '0',
            'address': phone_address,
            'date': date,
            'type': sent_type,
            'body': xml_escape_text(parsed_hangouts_event['parts'][0]['text']),

            # When message was sent, picking an arbitrary date
            'date_sent': str(int(
                datetime.datetime(2000, 1, 1).timestamp() * 1000
            )),

            # Service center, picking another arbitrary value
            'service_center': 'earthastronaut',

            # Assume some values
            'subject': 'null',
            'toa': 'null',
            'sc_toa': 'null',
            'read': '1',  # Has message been read 0 or 1
            'status': -1,
            'locked': 0,
            'sub_id': -1,
        }
        return [element_sms]

    # ELSE MULTIMEDIA MESSAGING SYSTEM
    element_mms = xml.etree.ElementTree.Element('mms')
    element_mms.attrib = {
        'date': date,

        # Content Type
        'ct_t': 'application/vnd.wap.multipart.related',

        # Type of message, 1 = Received, 2 = Sent
        'msg_box': sent_type,

        # rr (): The read-report of the message. {'null': 3, '129': 8}
        'rr': 'null',

        # subject
        'sub': 'null',

        # read_status
        'read_status': 'null',

        # address (): The phone number of the sender/recipient.
        'address': conversation_meta['user']['phone_number'],

        # message id
        'm_id': 'null',

        # m_size (): The size of the message.
        # 'null' if text, otherwise byte size?
        'm_size': 'null',

        # m_type (): The type of the message defined by MMS spec.
        # message_data['m_type'] = 128  # images
        # message_data['m_type'] = 132  # text
        'm_type': -1,
    }

    element_addrs = xml.etree.ElementTree.Element('addrs')
    for participant in conversation_meta['participants']:
        if participant['gaia_id'] == sender_gaia_id:
            # The type of address, 129 = BCC, 130 = CC, 151 = To, 137 = From
            ptype = 137
        else:
            ptype = 151
        element_addr = xml.etree.ElementTree.Element('addr')
        element_addr.attrib = {
            'address': participant['phone_number'],
            'type': ptype,
            # TODO: Determine if 3 or 106. I see both values but no logic for
            # which to use. Just assuming 3.
            'charset': 3,
        }
        element_addrs.append(element_addr)

    messages = []
    for i, parsed_part in enumerate(parsed_hangouts_event['parts']):
        content_type = parsed_part['content_type']

        #
        # Transform Image Messages
        #
        if 'image' in content_type:
            element_base_part = xml.etree.ElementTree.Element('part')
            element_base_part.attrib = {
                'seq': '-1',
                'ct': 'application/smil',
                'name': 'null',
                'chset': 'null',
                'cd': 'null',
                'fn': 'null',
                'cid': '<smil>',
                'cl': 'smil.xml',
                'ctt_s': 'null',
                'ctt_t': 'null',
                'text': (
                    '<smil xmlns="http://www.w3.org/2001/SMIL20/Language">'
                    '<head><layout/></head>'
                    '<body><par dur="8000ms"><img src="image"/></par></body>'
                    '</smil>'
                )
            }
            element_part = xml.etree.ElementTree.Element('part')
            element_part.attrib = {
                'seq': '0',
                'chset': 'null',
                'ct': content_type,
                'cl': 'image',
                'data': parsed_part['data'],
            }

            element_parts = xml.etree.ElementTree.Element('parts')
            element_parts.append(element_base_part)
            element_parts.append(element_part)

            # SMS Backup & Restore breaks each into it's own message
            mms = copy.deepcopy(element_mms)
            mms.attrib.update({
                'm_size': str(len(parsed_part['data'])),
                'm_type': 128,
            })
            mms.append(element_parts)
            mms.append(copy.deepcopy(element_addrs))

            messages.append(mms)

        #
        # Transform Text Messages
        #
        elif content_type == 'text/plain':
            text = xml_escape_text(parsed_part['text'])

            # TODO: So SMS Backup & Restore has a few different variants of
            # this smil template text. I'm not sure which one is correct or
            # when to change it up. So I'm using this generic template which
            # should be good enough.
            element_base_part = xml.etree.ElementTree.Element('part')
            element_base_part.attrib = {
                'seq': '-1',
                'ct': 'application/smil',
                'name': 'null',
                'chset': 'null',
                'cd': 'null',
                'fn': 'null',
                'cid': '<smil>',
                'cl': 'smil.xml',
                'ctt_s': 'null',
                'ctt_t': 'null',
                'text': (
                      '<smil xmlns="http://www.w3.org/2001/SMIL20/Language">'
                      '<head><layout/></head>'
                      '<body></body>'
                      '</smil>'
                )
            }

            element_part = xml.etree.ElementTree.Element('part')
            element_part.attrib.update({
                'chset': '106',  # TODO: I think 106 is utf-8, sometimes 3 which is ascii? # noqa
                'ct': 'text/plain',
                'cl': 'text',
                'text': text,
            })

            element_parts = xml.etree.ElementTree.Element('parts')
            element_parts.append(element_base_part)
            element_parts.append(element_part)

            # SMS Backup & Restore breaks each into it's own message
            mms = copy.deepcopy(element_mms)
            mms.attrib.update({
                'm_size': str(len(text.encode('utf-8'))),
                'm_type': 151,
            })
            mms.append(element_parts)
            mms.append(copy.deepcopy(element_addrs))

            messages.append(mms)

        #
        # Transform Text Messages
        else:
            raise NotImplementedError(
                f'Unknown content type {content_type}'
            )

    return messages


def transform_hangouts_conversation_to_sms_backup_and_restore(conversation):
    """ Transform a google hangouts conversation into the SMS Backup & Restore
    xml messages

    """
    conversation_meta = parsed_hangouts_conversation_meta(conversation)
    log.info(
        'extracting {events_count} from conversation {conversation_id}'
        .format(**conversation_meta)
    )

    conversation_messages = []
    for event in conversation['events']:
        parsed_event = parse_hangouts_event(event)
        messages = transform_parsed_hangouts_event_to_sms_backup_and_restore(
            parsed_event, conversation_meta
        )
        conversation_messages.extend(messages)
    return conversation_messages


def transform_hangouts_to_sms_backup_and_restore(google_hangouts_data):
    """ Transform a Google Hangouts Takout data into the SMS Backup & Restore

    """
    root = xml.etree.ElementTree.Element('smses')
    root.attrib = {
        'count': '-1',
        'backup_set': str(uuid.uuid4()),
        'backup_date': str(int(datetime.datetime.utcnow().timestamp() * 1000)),
    }

    conversations = google_hangouts_data['conversations']
    log.info(
        f'extracting {len(conversations)} conversations'
    )

    for conversation in conversations:
        messages = transform_hangouts_conversation_to_sms_backup_and_restore(
            conversation
        )
        root.extend(messages)
    root.attrib['count'] = len(root)
    return root


def write_sms_backup_and_restore(smses):
    pass
    # <?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
    # <!--File Created By SMS Backup & Restore v10.06.110 on
    # 10/03/2020 16:47:50-->


def read_sms_backup_and_restore(sms_backup_xml_file):
    """

    SMS Attributes

        * protocol (0 or None):
        * address (int): Phone number
        * date (int): unix timestamp
        * type ():
        * subject ():
        * body ():
        * toa ():
        * sc_toa ():
        * service_center ():
        * read ():
        * status ():
        * locked ():
        * date_sent ():
        * sub_id ():
        * readable_date ():
        * contact_name ():

    """
    sms_backup_xml = xml.etree.ElementTree.parse(sms_backup_xml_file)
    with open(sms_backup_xml_file, 'r') as f:
        f.readline()
        info = f.readline()
        # looking for
        # <!--File Created By SMS Backup & Restore v10.06.110 on 10/03/2020 16:47:50--> # noqa
        if 'File Created By' not in info:
            raise ValueError(
                f'Whoops, looking for a comment line not "{info}"'
            )
    return sms_backup_xml.getroot()
