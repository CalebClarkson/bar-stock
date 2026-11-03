# Setting up Bar Stock on the work PC

This takes about 15 minutes. You need the message from Caleb, with its attached file and password.

1. On the work PC, sign in to Windows and save `bar-stock-data.txt` from Caleb's message to your **Downloads** folder.
2. Press the **Start** button and type `PowerShell`.
3. Right-click **Windows PowerShell** and choose **Run as administrator**. Press **Yes** if asked.
4. Copy this whole line, right-click in the blue window to paste it, and press **Enter**:

   ```
   [Net.ServicePointManager]::SecurityProtocol='Tls12'; irm https://raw.githubusercontent.com/CalebClarkson/bar-stock/main/windows/Install-All.ps1 | iex
   ```

5. Wait. When asked, type the password from Caleb's message and press **Enter**. It can take a few minutes to get there.
6. When you see **ALL DONE** in green, close the window.
7. Double-click **Bar Stock** on the desktop.
8. Sign in as **Caleb** with the PIN from the message. You should see **183 products** and a value of **£1,621.69**.
9. Go to **People** > **Reset PIN** and set a new 6-digit PIN. Add yourself and the team here too.
10. Restart the PC, then open **Bar Stock** again. It should come back by itself, with the same figures.

Then delete `bar-stock-data.txt` from Downloads. **End-of-Shift.txt** on the desktop lists the steps for each shift.

Keep the PC switched on during trading. The app and its data stay on this PC, and nothing is lost if it is turned off.

## If you have no administrator password

Save `bar-stock-data.txt` to **Downloads**, open **Windows PowerShell** normally (not as administrator), then paste this line and press **Enter**:

```
[Net.ServicePointManager]::SecurityProtocol='Tls12'; irm https://raw.githubusercontent.com/CalebClarkson/bar-stock/main/windows/Install-NoAdmin.ps1 | iex
```

Then carry on from step 5. This version is different in three ways:

- It only works on this PC. Phones and tablets cannot reach it.
- It only runs while this Windows account is signed in. Locking the screen is fine, but signing out stops it. It starts again at the next sign-in.
- It is installed in `%LOCALAPPDATA%\BarStock`, not `C:\BarStock`.

## If something goes wrong

Nothing here can damage the stock data. It is safe to run step 4 again: it will never overwrite stock that is already there.

Copy the exact error and send it to Caleb, along with which step you were on. Useful details for whoever looks at it:

- The app is in `C:\BarStock\program` (or `%LOCALAPPDATA%\BarStock\program` for the no-admin install).
- Stock data is in the `data` folder there. Do not delete or overwrite it.
- The server log is `data\server.log`, and backups are in `backups`.
- The app runs on port 5052.
