# Hangouts to SMS

Google Hangouts uses a proprietary format to store messages, this code converts Hangouts data to an XML file for SMS Backup & Restore app to restore from. 


# Install

Code runs using python 3.7 with no external dependencies. Simply download the 
code and then use `python -m hangouts_to_sms` to run the CLI command (see Usage).


# Usage

This uses the "SMS Backup & Restore" to access your SMS/MMS data without the need for root access to the database of this data. 

The code converts Google Hangouts JSON to "SMS Backup & Restore" XML file which can then be restored to the phone. 

Optionally, the code will merge an the Hangouts XML with existing backup file. 


1. Download Google Hangouts Data.
    * Go to [Google Takeout](https://takeout.google.com/) to download your data.
    * click "De-select All"
    * Select "Hangouts" (JSON format is the default)
    * click "Next Step"
    * select Frequency: "Export Once", File Type: .zip
    * Download the file.
1. Install ["SMS Backup & Restore"](https://play.google.com/store/apps/details?id=com.riteshsahu.SMSBackupRestore&hl=en_US) from Google Play store
1. (optional) Create Backup of SMS using "SMS Backup & Restore".
1. (optional) Download existing SMS backup file (probably located `/sdcard/SMSBackupRestore`).
1. Run hangouts_to_sms to generate output xml (see below command). You can optionally provide the existing sms backup and it'll join them. 
1. Push the output xml to your phone. Location: `/sdcard/SMSBackupRestore`.
1. Open "SMS Backup & Restore" on your phone, click the menu then "Restore".
1. Select the file you just pushed and restore from that file. Tada!


Command to run. Replace filenames with your own. 
```
python -m hangouts_to_sms \
	/.../takeout-20200202T200002Z-001.zip \
	--output /.../hangouts-to-sms.xml \
	--existing /.../sms-20200202202002.xml
```

