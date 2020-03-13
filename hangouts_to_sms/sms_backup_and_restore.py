import datetime
from collections import Counter
import re
import xml.etree.ElementTree
import xml.sax.saxutils
import logging
import copy
import uuid

from hangouts_to_sms import hangouts

log = logging.getLogger(__name__)


def write_sms_backup_and_restore(xml_etree, filepath):
    """ Export to SMS Backup & Restore File
    """
    log.info(f'writing to {filepath}')

    with open(filepath, 'w') as fptr:
        now = datetime.datetime.now().isoformat()
        fptr.write("<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>\n")
        fptr.write(
            f"<!--File Created For SMS Backup & Restore v10.06.110 "
            f" By EarthAstronaut at {now}-->\n"
        )

    # TODO: Pretty print this. I don't know why the default write doesn't
    # have this option. I don't like how lxml does it. Especially for a large
    # file it makes no sense to create a giant string first then write it out.
    # better way is to recurse through the elements and append each one to the
    # file with the correct indentation. But that's too much work and
    # the SMS Backup & Restore didn't care.
    smses_tree = xml.etree.ElementTree.ElementTree(xml_etree)
    with open(filepath, 'ab') as fptr:
        smses_tree.write(fptr, encoding='utf-8')


def read_sms_backup_and_restore(sms_backup_xml_file):
    """ Read XML file from SMS Backup & Restore

    https://synctech.com.au/sms-backup-restore/fields-in-xml-backup-files/


    # Basic XML Structure

    Most of data is stored in attributes

    ```
    <?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
    <smses ...attributes>
        <sms ...attributes... />
        <mms ...attributes... >
            <parts>
                <part ...attributes... />
            </parts>
            <addrs>
                <addr ...attributes... />
            </addrs>
        </mms>
        ...
    </smes>
    ```

    # SMS Attributes 

    Tag sms has the following attributes

        * protocol (0): Some protocol number which i found always '0'
        * address (int): Phone number
        * date (int): The Java date representation (including millisecond) of 
            the time when the message was sent/received. Check out 
            www.epochconverter.com for information on how 
            to do the conversion from other languages to Java.
        * type (int): 1 = Received, 2 = Sent, 3 = Draft, 4 = Outbox, 5 = Failed, 6 = Queued.  # noqa
            * 1 : mostly voicemail messages        
            * 2 : text message

        * body (string):
        * read (bool 0/1): Has message been read
        * date_sent (int): unix timestamp milliseconds of when message is sent
        * readable_date (string): Optional. Same as date.
        * contact_name (string): Optional. Name of the contact. 
        * subject (string): Subject of the message, its always 'null' in case of SMS messages.
        * toa (string): n/a, defaults to null. IGNORE
        * sc_toa (string): n/a, defaults to null. IGNORE
        * service_center (string):  The service center for the received message, null in case of sent messages. IGNORE. # noqa
        * status (int): None = -1, Complete = 0, Pending = 32, Failed = 64. IGNORE currently all -1. # noqa
        * locked (bool 0/1): TODO: ignore for now {'0': 102}
        * sub_id (int): TODO: ignore for now, Most are '-1' {'-1': 101, '1': 1} the 1 is a voicemail # noqa 

    # MMS Attributes

        * date (int): The Java date representation (including millisecond) of the time when the message was sent/received. Check out www.epochconverter.com for information on how to do the conversion from other languages to Java.
        * ct_t (): The Content-Type of the message, usually "application/vnd.wap.multipart.related"
        * msg_box (): The type of message, 1 = Received, 2 = Sent, 3 = Draft, 4 = Outbox
        * rr (): The read-report of the message. {'null': 3, '129': 8}
        * sub (): The subject of the message, if present.
        * read_status (): The read-status of the message.
        * address (): The phone number of the sender/recipient.
        * m_id (): The Message-ID of the message
        * read (): Has the message been read
        * m_size (): The size of the message.
        * m_type (): The type of the message defined by MMS spec. 132 or 128
        * readable_date (string): Optional. Same as date.
        * contact_name (string): Optional. Name of the contact.

        * seen (bool 0/1):
        * sub_cs (): 'null'
        * resp_st (): 'null'
        * retr_st (): 'null'
        * d_tm (): 'null'
        * text_only (bool 0/1):
        * exp (): ?? 'null' and '604800'
        * locked (0/1):
        * st (): 'null'
        * retr_txt_cs (): 'null'
        * retr_txt (): 'null'
        * creator (): e.g. com.android.providers.telephony, xyz.klinker.messenger
        * date_sent (): Java date when sent
        * rpt_a (): 'null'
        * ct_cls (): 'null'
        * pri (): ?? 'null' and '129'
        * sub_id (): '-1'
        * tr_id (): ?? many values and some 'null'
        * resp_txt (): 'null'
        * ct_l (): ?? many values and some 'null'
        * m_cls (): ?? 'null' and 'personal'
        * d_rpt (): 'null' and '129'
        * v (): '18' ???

    # MMS Part Attributes

        * seq (int): The order of the part. Starting at -1
        * ct (): The content type of the part. e.g. application/smil, text/plain, image/jpeg, image/png
        * name (): The name of the part. e.g. smil.xml, text.000000.txt, null
        * chset (): The charset of the part. e.g. null, 106, 3
        * cl (): The content location of the part. e.g. smil.xml, text.000000.txt, image, text
        * text (): The text content of the part.
        * data (): OPTIONAL. The base64 encoded binary content of the part.

        * cd ():
        * fn ():
        * cid ():
        * ctt_s ():
        * ctt_t ():

    # MMS Addrs Attributes

        * address (): The phone number of the sender/recipient.
        * type (): The type of address, 129 = BCC, 130 = CC, 151 = To, 137 = From
        * charset (): Character set of this entry. Example: 3, 106. WHAT ARE THESE??

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
    log.info(f'Read file {sms_backup_xml}\n{info}')
    major, minor, patch = re.match(r'.*v(\d*)\.(\d*)\.(\d*)', info).groups()
    if major != '10' and minor != '06':
        log.warning(
            f'This script was created using SMS Backup & Restore v10.06.110 '
            f'and may not work with v{major}.{minor}.{patch} \n'
            f'BUT I\'LL GIVE IT A TRY!!!!'
        )

    root = sms_backup_xml.getroot()
    root.tail = '\n'
    return root


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
        sent_type = '2'  # Sent
    else:
        sent_type = '1'  # Received

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
            'status': '-1',
            'locked': '0',
            'sub_id': '-1',
        }
        return [element_sms]

    # ELSE MULTIMEDIA MESSAGING SYSTEM
    element_mms = xml.etree.ElementTree.Element('mms')
    element_mms.attrib = {
        'date': date,

        # Content Type
        'ct_t': 'application/vnd.wap.multipart.related',

        # Type of message, 1 = Received, 2 = Sent
        'msg_box': str(sent_type),

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
        'm_type': 'null',
    }

    element_addrs = xml.etree.ElementTree.Element('addrs')
    for participant in conversation_meta['participants']:
        if participant['gaia_id'] == sender_gaia_id:
            # The type of address, 129 = BCC, 130 = CC, 151 = To, 137 = From
            ptype = '137'
        else:
            ptype = '151'
        element_addr = xml.etree.ElementTree.Element('addr')
        element_addr.attrib = {
            'address': str(participant['phone_number']),
            'type': str(ptype),
            # TODO: Determine if 3 or 106. I see both values but no logic for
            # which to use. Just assuming 3.
            'charset': '3',
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
                'm_type': '128',
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
                'm_type': '151',
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


def transform_hangouts_conversation_to_sms_backup_and_restore(conversation, message_counter=0, message_count=None):  # noqa
    """ Transform a google hangouts conversation into the SMS Backup & Restore
    xml messages

    """
    conversation_meta = hangouts.parsed_hangouts_conversation_meta(
        conversation)
    log.info(
        'extracting {events_count} from conversation {conversation_id}'
        .format(**conversation_meta)
    )

    conversation_messages = []
    for event in conversation['events']:
        parsed_event = hangouts.parse_hangouts_event(event)
        messages = transform_parsed_hangouts_event_to_sms_backup_and_restore(
            parsed_event, conversation_meta
        )
        conversation_messages.extend(messages)
        message_counter += 1
        if message_count and message_counter > message_count:
            break
    return conversation_messages


def transform_hangouts_data(google_hangouts_data, message_count=None):
    """ Transform a Google Hangouts Takout data into the SMS Backup & Restore

    """
    root = xml.etree.ElementTree.Element('smses')
    root.tail = '\n'
    root.attrib = {
        'count': '-1',
        'backup_set': str(uuid.uuid4()),
        'backup_date': str(int(datetime.datetime.utcnow().timestamp() * 1000)),
    }

    conversations = google_hangouts_data['conversations']
    log.info(
        f'extracting {len(conversations)} conversations'
    )
    message_counter = 0

    for conversation in conversations:
        messages = transform_hangouts_conversation_to_sms_backup_and_restore(
            conversation,
            message_counter=message_counter, message_count=message_count,
        )
        root.extend(messages)
        if message_count and message_counter > message_count:
            logging.debug(
                f'reached messaged limit {message_count} with {message_counter}'
            )
            break
    root.attrib['count'] = str(len(root))
    return root


def smses_stats(smses, log_results=False):
    """ Count some statistics about the SMS Backup & Restore smses messages
    """

    counter = Counter()
    contacts_set = set()
    for i, msg in enumerate(smses):
        counter['messages'] += 1

        if msg.tag == 'sms':
            contacts_set.add(msg.attrib['address'])

            sent_type = msg.attrib['type']

            body = msg.attrib['body']
            # special error handling
            if body.startswith('ERROR'):
                _, error_type, error_msg = body.split(hangouts.MESSAGE_ERROR_DELIM)  # noqa
                if error_type == hangouts.MESSAGE_ERROR_IMAGE_NOT_FOUND:
                    counter['mms'] += 1
                    counter[error_type] += 1
                else:
                    raise NotImplementedError(
                        f'fix counter for this error {error_type}'
                    )
            else:
                counter['sms'] += 1

        else:
            counter['mms'] += 1
            sent_type = msg.attrib['msg_box']
            for addr in msg[1]:
                contacts_set.add(addr.attrib['address'])

        if sent_type == '1':
            counter['received'] += 1
        elif sent_type == '2':
            counter['sent'] += 1
        else:
            raise ValueError(f'unknown {sent_type}')

    counter['contacts'] += len(contacts_set)

    if log_results:
        counter_fmt = '\n'.join([f'{k}:{v}' for k, v in counter.items()])
        log.info(f'STATS\n{counter_fmt}')

    return counter
