# Gmail Email Assistant

This application provides a conversational interface to access and manage your Gmail account.

## Setup Instructions

### 1. Create a Google Cloud Project

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable the Gmail API for your project

### 2. Create OAuth 2.0 Credentials

1. In your Google Cloud project, go to **APIs & Services** > **Credentials**
2. Click **Create Credentials** and select **OAuth client ID**
3. Set Application Type to **Desktop app**
4. Name your OAuth client
5. Click **Create**
6. Download the JSON credentials file

### 3. Set Up Credentials in the Application

1. Rename the downloaded file to `gmail_cred.json`
2. Place it in the project root directory (or set the `GMAIL_CREDS_FILE` environment variable to point to your file)

### 4. Run the Application

1. Start the application with `python src/gmail/app.py`
2. On first run, you'll be prompted to authorize the application in your browser
3. Log in with your Google account and grant the required permissions
4. The token will be saved to a file called `token.json` for future use

## Troubleshooting

### "Failed to connect to email server" Error

This error indicates that the application cannot find or use the necessary credentials:

1. Make sure the `gmail_cred.json` file exists in the project root directory
2. Check that the credentials have the correct OAuth 2.0 scopes (`https://www.googleapis.com/auth/gmail.modify`)
3. If you've recently revoked permissions, delete the `token.json` file and restart

### Invalid Credentials Error

If your credentials have expired or been revoked:

1. Delete the `token.json` file from the project root directory
2. Restart the application, which will prompt you to re-authenticate

## Security Notes

The application stores your OAuth token locally. Make sure to:

1. Keep your credentials file secure
2. Do not commit credentials to version control
3. Revoke access in the Google account settings if your credentials are compromised
