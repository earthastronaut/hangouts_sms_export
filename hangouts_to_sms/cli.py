#!env python
import argparse
import logging

from hangouts_to_sms import hangouts


parser = argparse.ArgumentParser()
parser.add_argument(
    'google_hangouts_zip_file',
    help='Zip file from Google Takeout takeout.google.com, see README',
)
parser.add_argument(
    '-l', '--loglevel',
    default='INFO',
    help='Log Level, "notset" will remove all logging. Default: INFO',
)
parser.add_argument(
    '-x', '--existing',
    help='Include existing XML file from SMS Backup & Restore',
)
parser.add_argument(
    '--message-count',
    type=int,
    help='Maximum number of messages (useful for testing)',
)
parser.add_argument(
    '-o', '--output',
    required=True,
    help='Output XML file for SMS Backup & Restore'
)


def configure_logging(pargs):
    logging.config.dictConfig({
        'version': 1,
        'disable_existing_logging': True,
        'formatters': {
            'default': (
                "{{{level}': '{levelname}', 'time':'{asctime}', \n"
                "'name': '{name}', 'lineno': '{lineno}, \n"
                "'message': '{message}'}}"
            ),
            'datefmt': '%Y-%m-%dT%H:%M:%S',
            'style': '{',
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'default',
            }
        },
        'root': {
            'level': pargs.loglevel,
            'handlers': ['default'],
        },
    })


def main():
    pargs = parser.parse_args()
    configure_logging(pargs)

    # extract parameters
    google_hangouts_zip_file = pargs.google_hangouts_zip_file
    message_count = pargs.message_count
    existing_sms_backup_restore_file = pargs.existing
    output_xml_file = pargs.output

    with open(output_xml_file, 'w') as f:
        f.write('this is a check')

    # google convert
    google_hangouts_data = hangouts.read_google_hangouts_message_data(
        google_hangouts_zip_file)
    smses_google = hangouts.transform_hangouts_to_sms_backup_and_restore(
        google_hangouts_data, message_count=message_count)

    # append existing if provided
    if existing_sms_backup_restore_file:
        smses = hangouts.read_sms_backup_and_restore(
            existing_sms_backup_restore_file)

        smses_google.extend(smses)

    smses_google.attrib['count'] = str(len(smses_google))
    hangouts.write_sms_backup_and_restore(
        smses_google, output_xml_file,
    )
