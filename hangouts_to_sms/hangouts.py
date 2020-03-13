import os
import datetime
import json
import zipfile
import logging
import base64
import tempfile
import time
import random
import urllib


MESSAGE_ERROR_IMAGE_NOT_FOUND = 'IMAGE NOT FOUND'
MESSAGE_ERROR_TYPES = [
    MESSAGE_ERROR_IMAGE_NOT_FOUND
]
MESSAGE_ERROR_DELIM = ':: '

log = logging.getLogger(__name__)


def generate_error_text(error_type, error_msg):
    if error_type not in MESSAGE_ERROR_TYPES:
        raise ValueError(
            f'error_type {error_type} not in {MESSAGE_ERROR_TYPES}'
        )
    if MESSAGE_ERROR_DELIM in error_msg:
        raise ValueError(
            f'error_msg can not contain delimiter\n'
            f'"{MESSAGE_ERROR_DELIM}" in "{error_msg}"'
        )
    return MESSAGE_ERROR_DELIM.join(
        'ERROR',
        error_type,
        error_msg,
    )


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


def retrieve_image_data(url, event_id, max_backoff_time=10):
    cache_key = event_id
    if cache_key:
        cache_file = os.path.join(
            tempfile.gettempdir(),
            f'hangouts_to_sms_{cache_key}.json'
        )
        if os.path.exists(cache_file):
            log.debug(f'Image from cache file {cache_file}')
            with open(cache_file) as f:
                return json.load(f)

    retries = 0
    while True:
        retries += 1
        try:
            with urllib.request.urlopen(url) as resp:
                content = resp.read()
        except urllib.error.HTTPError as error:
            if error.code == 500:
                delay = (0.5 * retries) ** 2 + random.randint(0, 1000) / 1000.0
                if delay > max_backoff_time:
                    error.msg = (
                        f'Reached maximum backoff time after {retries} retries'
                    )
                    raise

                log.debug(
                    f'URL returned 500, retry {retries} delaying {delay}'
                )
                time.sleep(delay)
                continue
            elif error.code == 404:
                log.warning(
                    f'Image for event_id = {event_id} received 404 error'
                )
                return {
                    'error': error,
                    'content_type': 'text/plain',
                    'text': generate_error_text(
                        MESSAGE_ERROR_IMAGE_NOT_FOUND,
                        url,
                    )
                }
            else:
                raise
        break

    content_type = resp.headers['content-type']
    options = ['image/jpeg', 'image/png', 'image/gif']
    log.debug(f'response returned {resp.status} with {content_type}')
    # 'text/plain'
    if content_type not in options:
        raise ValueError(
            f'unknown content type {content_type} not in {options}'
        )
    image_data = base64.b64encode(content).decode('ascii')
    data = {
        'content_type': content_type,
        'data': image_data,
    }
    if cache_key:
        log.debug(f'Writing cache file {cache_file}')
        with open(cache_file, 'w') as f:
            json.dump(data, f)
    return data


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
    event_id = event['event_id']
    parsed['event_id'] = event_id

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

            log.info(f'Downloading image event id {event_id}')

            parsed['parts'].append(
                retrieve_image_data(url, event_id)
            )
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
