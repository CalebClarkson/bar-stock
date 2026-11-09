# Setting up Bar Stock on a Windows PC

This takes about 15 minutes and needs an internet connection. The app and all its data stay on this PC.

1. On the PC behind the bar, press the **Start** button and type `PowerShell`.
2. Right-click **Windows PowerShell** and choose **Run as administrator**. Press **Yes** if asked.
3. Copy this whole line, right-click in the blue window to paste it, and press **Enter**:

   ```
   [Net.ServicePointManager]::SecurityProtocol='Tls12'; irm https://raw.githubusercontent.com/CalebClarkson/bar-stock/main/windows/Install-All.ps1 | iex
   ```

4. Wait. When asked, type your name and choose a 6-digit PIN. This makes you the first admin.
5. When you see **ALL DONE** in green, close the window.
6. Double-click **Bar Stock** on the desktop and sign in with your PIN.
7. Open **Settings**:
   - **People**: add your team. Everyone can view figures and upload the night's Square sales; tick the jobs
     (stocktakes, wastage, batches) each person may also do.
   - **Products**: add what you stock, or import a stocktake spreadsheet from the Stocktake screen.
   - **Look & feel**: add your logo, name and colours.
8. Do a first stocktake, then upload the night's Square sales after each shift. **End-of-Shift.txt** on the desktop
   lists the steps.

Keep the PC switched on during trading. Nothing is lost if it is turned off.

## Moving existing stock from another PC

On the old PC, export the data with a password:

```
set OSB_BUNDLE_PASSWORD=choose-a-strong-password
.venv\Scripts\python.exe manage.py export-data bar-stock-data.txt
```

Save `bar-stock-data.txt` to the new PC's **Downloads** folder before step 3. The installer finds it and asks for the
password instead of creating a new admin. Delete the file from Downloads afterwards.

## If you have no administrator password

Open **Windows PowerShell** normally (not as administrator), paste this line and press **Enter**:

```
[Net.ServicePointManager]::SecurityProtocol='Tls12'; irm https://raw.githubusercontent.com/CalebClarkson/bar-stock/main/windows/Install-NoAdmin.ps1 | iex
```

Then carry on from step 4. This version is different in three ways:

- It only works on this PC. Phones and tablets cannot reach it.
- It only runs while this Windows account is signed in. Locking the screen is fine, but signing out stops it. It
  starts again at the next sign-in.
- It is installed in `%LOCALAPPDATA%\BarStock`, not `C:\BarStock`.

## If something goes wrong

Nothing here can damage the stock data. It is safe to run the install line again: it never overwrites stock that is
already there.

- The app is in `C:\BarStock\program` (or `%LOCALAPPDATA%\BarStock\program` for the no-admin install).
- Stock data, your logo and your venue's matching rules are in the `data` folder there. Do not delete it.
- The server log is `data\server.log`, and backups are in `backups`.
- The app runs on port 5052.
