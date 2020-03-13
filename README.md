# Hangouts to SMS

Google hangouts uses a proprietary format to store messages, this converts it XML for SMS Backup & Restore app to restore from. 


# Install

Code runs using python 3.7 with no external dependencies. Simply download the 
code and then use `python -m hangouts_to_sms` to run the CLI command.


# Usage

This uses the SMS Backup & Restore to access your SMS/MMS data without the need for root access to the database of this data. 

I then convert Google Hangouts data to SMS Backup & Restore file and merge with existing backup file. 


1. Download Google Hangouts Data
    * Go to [Google Takeout](https://takeout.google.com/) to download your data.
    * click "De-select All"
    * Select "Hangouts" (JSON format is the default)
    * click "Next Step"
    * select Frequency: "Export Once", File Type: .zip
    * Download the file.
1. Install ["SMS Backup & Restore"](https://play.google.com/store/apps/details?id=com.riteshsahu.SMSBackupRestore&hl=en_US) from Google Play store
1. (optional) Create Backup of SMS using SMS Backup & Restore
1. (optional) Download existing SMS backup file
	* probably located `/sdcard/SMSBackupRestore`
1. Run hangouts_to_sms to generate output xml (see below command). You can optionally provide the existing sms backup and it'll join them. 
1. Push the output xml to your phone. Location: '/sdcard/SMSBackupRestore'
1. Open "SMS Backup & Restore" on your phone, click the menu then "Restore"
1. Select the file you just pushed and restore from that file


Command to run is this with the file names replaced

```
python -m hangouts_to_sms \
	/.../takeout-20200202T200002Z-001.zip \
	-o /.../hangouts-to-sms.xml \
	-x /.../sms-20200202202002.xml
```

