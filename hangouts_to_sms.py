import datetime
import json
import xml.etree.ElementTree
import zipfile
import logging
import base64

import requests


def read_google_hangouts_message_data(google_takeout_zip_file):
    """ Read the zip file [Google Takeout](https://takeout.google.com/)
    generates and extract the `Takeout/Hangouts/Hangouts.json` data
    """
    hangouts_data_fp = 'Takeout/Hangouts/Hangouts.json'
    logging.info(
        f'Reading {hangouts_data_fp} from "{google_takeout_zip_file}" archive'
    )

    with zipfile.ZipFile(google_takeout_zip_file) as zf:
        f = zf.open(hangouts_data_fp)
        data = json.load(f)
        return data


def write_sms_backup(data):
    pass
    # <?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
    # <!--File Created By SMS Backup & Restore v10.06.110 on 10/03/2020 16:47:50-->


def read_sms_backup(sms_backup_xml_file):
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


def extract_conversation_meta(conversation):
    """ Extract the meta data about the conversation including participants
    """
    # conversation.conversation
    convo = conversation['conversation']['conversation']

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
        gaia_id = participant['id']['gaia_id']

        if gaia_id == user_gaia_id:
            user = {
                'gaia_id': gaia_id,
                'phone_number': participant['fallback_name'],
            }
        else:
            if 'phone_number' not in participant:
                raise NotImplementedError('whoop! no participant phone number')
            participants.append({
                'gaia_id': gaia_id,
                'phone_number': participant['phone_number']['e164'],
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
        'user': user,
        'participants': participants,
        'participants_count': len(participants),
    }


def transform_hangouts_event_to_backup(event, conversation_meta):
    # collect relevant information for sms or mms
    message_data = {}
    message_parts = []

    # conversation_id
    # conversation_id.id matches parent
    # event['conversation_id']

    # sender_id
    # keys: gaia_id, chat_id
    # event['sender_id']

    # example: '1576525471673269' probably unix
    # timestamp / 1000 / 1000 in nanosec
    date = int(event['timestamp']) / 1000

    # keys: 'notification_level', 'user_id.gaia_id', 'user_id.chat_id'
    # event['self_event_state']

    # event_id
    # example: '8QLSTrym2cg92booEdZ5wx'
    # event['event_id']

    # advances_sort_timestamp
    # type: boolean
    # event['advances_sort_timestamp']

    # event_otr
    # type: string
    # values: ON_THE_RECORD
    # event['event_otr']

    # delivery_medium.medium_type
    # values: GOOGLE_VOICE_MEDIUM, BABEL_MEDIUM, UNKNOWN_MEDIUM'
    # event['delivery_medium']

    # event_version
    # example: '1576525471673269'
    # event['event_version']

    # event_type
    # type: string
    # values: SMS, REGULAR_CHAT_MESSAGE, VOICEMAIL
    event_type = event['event_type']
    if event_type == 'REGULAR_CHAT_MESSAGE':
        is_sms = False  # is mms
    else:
        is_sms = True

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
            #     segment_link_display_url = segment_link_data.get('display_url')

            if is_sms:
                message_data.setdefault('body', '')

                if segment_type == 'LINE_BREAK':
                    message_data['body'] += '&#10'
                elif segment_type == 'TEXT':
                    message_data['body'] += segment_text
                elif segment_type == 'LINK':
                    # links are stored separately in google hangouts
                    # but are really just part of the message (or whole message)
                    # so I'm making them part of it with spaces
                    message_data['body'] += f' {segment_text} '
                else:
                    raise ValueError(f'unknown segment type {segment_type}')
            else:
                pass

    # chat_message.attachment
    # required: false
    # type: list with objects
    # keys: embed_item, id
    attachments = message_content.get('attachment', [])
    if len(attachments):
        # my sample only ever had 1 attachment
        if len(attachments) > 1:
            raise NotImplementedError(
                f'Determine handling of {len(attachments)} attachments'
            )

        attachment = attachments[0]

        # attachment.embed_item
        # required: true
        attachment_embed_item = attachment['embed_item']

        attachment_embed_item_type = attachment_embed_item['type']

        # attachment.id
        # required: true
        attachment_id = attachment['id']

        is_sms = False
        # attachment_embed_item.type = ['PLACE_V2', 'THING_V2', 'THING']
        # appears to be for maps data but I can ignore, just a regular link
        if False and attachment_embed_item_type == ['PLUS_PHOTO']:
            url = attachment_embed_item['plus_photo']['url']
            resp = requests.get(url)
            content_type = resp.headers['Content-Type']
            options = ['image/jpeg', 'image/png']
            if content_type not in options:
                raise ValueError(
                    f'unknown content type {content_type} not in {options}'
                )
            image_data = base64.b64encode(resp.content).decode('ascii')

            message_parts.append({
                'seq': len(message_parts) - 1,
                'chset': 'null',
                'ct': content_type,
                'cl': 'image',
                'data': image_data
            })

            # TODO: raise NotImplementedError('chset is actually unknown!!!')

    # chat_message.annotation
    # required: false
    # type: list with objects
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
        annotation_type = annotation['type']

        # annotation.value
        # type: str
        # description: all values I had were empty string
        annotation_value = annotation['value']

        if annotation_value != '':
            raise NotImplementedError(
                f'Oh! You found a non-empty annotation {annotation_value}'
            )

    n = conversation_meta['participants_count']
    if is_sms and n > 1:
        # actually converting from google hangouts sms to mms
        is_sms = False
        raise NotImplementedError(f'Convert participants')

    if is_sms:
        assert conversation_meta['participants_count'] == 1
        phone_address = conversation_meta['participants'][0]['phone_number']

        return {
            'tag': 'sms',

            'protocol': '0',
            'address': phone_address,

            'date': date,

            # type (int): 1 = Received, 2 = Sent
            # TODO: WHICH IS IT!!!!!
            'type': 1,

            'body': message_data['body'],

            # read (bool 0/1): Has message been read
            'read': '1',

            'date_sent': int(datetime.datetime(2000, 1, 1).timestamp() * 1000),

            'subject': 'null',
            'toa': 'null',
            'sc_toa': 'null',
            'service_center': 'earthastronaut',
            'status': -1,
            'locked': 0,
            'sub_id': -1,
        }
    else:
        raise NotImplementedError('hehe')
        return {
            'tag': 'mms',

            'date': date,

            # Content Type
            'ct_t': 'application/vnd.wap.multipart.related',

            # Type of message, 1 = Received, 2 = Sent
            'msg_box': 1,

            # rr (): The read-report of the message. {'null': 3, '129': 8}
            'rr': 'null',

            # subject
            'sub': 'null',

            # read_status
            'read_status': 'null',

            # address (): The phone number of the sender/recipient.
            'address': phone_address,

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


def transform_hangouts_conversation_to_backup(conversation):
    try:
        conversation_meta = extract_conversation_meta(conversation)
    except NotImplementedError as e:
        print(e)
        return []

    events = conversation['events']
    logging.info(
        f'extracting {len(events)} from conversation'
    )

    events_transformed = []
    for event in events:
        try:
            et = transform_hangouts_event_to_backup(event, conversation_meta)
            events_transformed.append(et)
        except NotImplementedError:
            pass
    return events_transformed


def transform_conversations_to_xml_backup_messages(google_hangouts_data):
    conversations = google_hangouts_data['conversations']
    logging.info(
        f'extracting {len(conversations)} conversations'
    )
    conversation_events_transformed = []
    for conversation in conversations:
        conversation_events_transformed.extend(
            transform_hangouts_conversation_to_backup(conversation)
        )

    xml_backup_messages = []
    for event in conversation_events_transformed:
        event = event.copy()
        tag = event.pop('tag')
        element = xml.etree.ElementTree.Element(tag)
        element.attrib = event
        xml_backup_messages.append(element)
    return xml_backup_messages
