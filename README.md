# Hangouts to SMS

Google hangouts uses a proprietary format to store messages, this converts it XML for SMS Backup & Restore app to restore from. 


# Method

This uses the SMS Backup & Restore to access your SMS/MMS data without the need for root access to the database of this data. 

I then convert Google Hangouts data to SMS Backup & Restore file and merge with existing backup file. 


1. Download Google Hangouts Data
    * Go to [Google Takeout](https://takeout.google.com/) to download your data.
    * click "De-select All"
    * Select "Hangouts" (JSON format is the default)
    * click "Next Step"
    * select Frequency: "Export Once", File Type: .zip
    * Download the file.
1. Install [SMS Backup & Restore](https://play.google.com/store/apps/details?id=com.riteshsahu.SMSBackupRestore&hl=en_US) from Google Play store
1. Create Backup of SMS using SMS Backup & Restore
1. Download SMS backup file

