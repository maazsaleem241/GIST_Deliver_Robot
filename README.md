# GIST Robots Delivery Project: Teleoperated Delivery Robot

This project lets you drive a four-wheel delivery robot from a laptop over Wi-Fi while you watch a live video feed from the robot's camera.

The robot carries two small computers. A **Raspberry Pi** handles the camera and the network connection. An **Arduino with a QGPMaker motor shield** drives the four DC motors. On the laptop, a "cockpit" window shows the live video on the left and a control dashboard on the right, and you drive with the W / A / S / D keys.

The robot has mecanum wheels, but the code drives it like a tank (differential or "skid-steer" drive). Both wheels on the left side always receive the same command, and so do both wheels on the right side. The robot turns by running the two sides at different speeds or in opposite directions.

**The driving controls were fine-tuned on the real robot.** The speeds, steering strength, left/right balance and turn compensation were adjusted through test drives until the robot drove straight, turned evenly in both directions and stayed easy to control. All tuned values are listed in [Fine-tuned control parameters](#5-fine-tuned-control-parameters).

### Quick start (if you have done this before)

1. Upload `mecanum_serial_driver/` to the Arduino (once), then plug the Arduino into the Pi by USB.
2. On the Pi, run `python3 robot_server.py`.
3. On the laptop, set `ROBOT_IP` in `laptop_cockpit.py`, then run `python laptop_cockpit.py`.
4. Drive with **W/A/S/D**. Press **Space** to stop, **E** to switch to Booster mode and **Q** to quit.

Step-by-step instructions for first-time users are in [How to run it](#6-how-to-run-it).

---

## 1. Repository contents

```
GIST_Robots_Delivery_Project/
├── laptop_cockpit.py               ← runs on the LAPTOP
├── robot_server.py                 ← runs on the RASPBERRY PI (on the robot)
└── mecanum_serial_driver/          ← uploaded to the ARDUINO (on the robot)
    ├── mecanum_serial_driver.ino
    ├── QGPMaker_MotorShield.cpp
    ├── QGPMaker_MotorShield.h
    ├── Adafruit_MS_PWMServoDriver.cpp
    └── Adafruit_MS_PWMServoDriver.h
```

| File | Runs on | Job |
|---|---|---|
| `laptop_cockpit.py` | Laptop | Shows the video, reads your keys, calculates the left and right wheel values and sends them to the robot. |
| `robot_server.py` | Raspberry Pi | Streams the camera to the laptop and passes drive commands to the Arduino. |
| `mecanum_serial_driver.ino` | Arduino | Turns each drive command into motor power and direction for the four motors. |
| `QGPMaker_MotorShield.*`, `Adafruit_MS_PWMServoDriver.*` | Arduino | Library code for the motor shield, kept inside the sketch folder so nothing has to be installed. |

---

## 2. How the system works

```
 LAPTOP (laptop_cockpit.py)        RASPBERRY PI (robot_server.py)        ARDUINO (mecanum_serial_driver.ino)

 shows live video   ◄──── video frames ─────  camera → JPEG
 reads keys → L, R  ───── "L:x,R:y\n" ─────►  forwards text ──── USB serial ────►  L, R → PWM → 4 motors
                     (Wi-Fi, TCP port 8089)                     (115200 baud)
```

A single TCP network connection carries traffic both ways. Video goes from the Pi to the laptop, and drive commands go from the laptop to the Pi. The Pi passes each drive command to the Arduino over its USB cable.

A drive command is one short line of text:

```
L:-0.200,R:0.200
```

`L` is the value for the left-side motors and `R` is the value for the right-side motors. The sign sets the direction and the size sets how much power the motors get.

---

## 3. What each program does

### 3.1 `robot_server.py` (Raspberry Pi)

1. **Connects to the Arduino** on `/dev/ttyACM0` at 115200 baud, then waits 2 seconds. Opening the serial port resets the Arduino, and it needs a moment to start up. If the Arduino is not found, the script stops and prints `❌ Arduino Failed`.
2. **Opens the camera** (device 0) at 640×480.
3. **Waits for the laptop** on TCP port 8089 and accepts one connection.
4. **Runs two jobs at the same time** once the laptop connects:
   - A *command thread* receives text from the laptop. Every message that starts with `L:` is written straight to the Arduino, and the Pi terminal prints `Routing to Wheels: ...`.
   - The *video loop* reads a camera frame, compresses it to JPEG at quality 55 and packs it with Python's `pickle`. It then sends the frame with an 8-byte length header in front, so the laptop knows where each frame ends.
5. **Shuts down safely.** When the laptop disconnects, or you press Ctrl+C, the server sends `L:0.0,R:0.0` (stop) to the Arduino, releases the camera and closes the connection. The server handles one driving session and then exits, so you start it again for the next session.

### 3.2 `laptop_cockpit.py` (Laptop)

1. **Connects** to `ROBOT_IP` on port 8089. The robot server must already be running.
2. **Opens a resizable window** called `LAPTOP TELEOP COCKPIT`, starting at 1280×720.
3. **Repeats these steps for every video frame:**
   1. It receives the 8-byte header and then the frame, and decodes the frame into an image.
   2. It reads the keyboard with the `keyboard` library.
   3. It calculates the left and right values (see [Section 4](#4-driving-controls-and-the-drive-math)).
   4. It sends `L:<left>,R:<right>` to the robot.
   5. It draws the window. The video fills the left 75%, and the dashboard fills the right 25%. The pressed key lights up green, the mode badge reads NORMAL (blue) or BOOSTER (orange), and the bottom line shows the active key. The layout rescales when you resize the window.
4. **Stops cleanly.** When you press Q, an error happens or the connection drops, it sends a final stop command and closes.

Commands are sent inside the video loop, so the robot receives one new command for every video frame.

### 3.3 `mecanum_serial_driver.ino` (Arduino)

- **`setup()`** starts serial at 115200 baud and starts the motor shield (I2C address `0x60`) with a 50 Hz PWM frequency. It then stops all motors.
- **`loop()`** collects incoming characters until it receives a newline (`\n`). It then checks that the line contains `L:` and `,R:`, reads the two numbers and calls `controlMotors()`.
- **`controlMotors(left, right)`** sets the power and direction of each side:
  - **Power:** `|value| × 600`, capped at 255. The left value is multiplied by `LEFT_TRIM = 0.90` first.
  - **Direction:** a value of 0 or more runs the motor `FORWARD`, and a negative value runs it `BACKWARD`. These are the shield's directions.
  - **Motors 1 (front-left) and 2 (rear-left)** get the left command. **Motors 3 (front-right) and 4 (rear-right)** get the right command.
- The Arduino keeps running the last command it received until a new one arrives. It has no timeout.

**Why the left value is negative when driving forward:** the left motors are mounted and wired so that they must spin in the shield's `BACKWARD` direction to move the robot forward. `laptop_cockpit.py` flips the sign of the left value to match. Driving forward therefore sends `L:-0.200,R:0.200`.

**The library files.** `QGPMaker_MotorShield` is the shield's library. The shield has a PCA9685 PWM chip, and each DC motor uses two of the chip's channels (IN1 and IN2), which feed an H-bridge. `FORWARD` sends PWM on IN1 with IN2 low, `BACKWARD` does the reverse, and `RELEASE` sets both low so the motor coasts. `setSpeed()` takes 0–255 and multiplies it by 16 to fit the chip's 12-bit range (0–4095). The library also contains stepper and servo code, which this project does not use. `Adafruit_MS_PWMServoDriver` is the low-level I2C driver for the PCA9685. It sets the PWM frequency and writes the duty-cycle registers.

---

## 4. Driving controls and the drive math

### Controls

| Key | What it does |
|---|---|
| **W** | Drive forward |
| **S** | Drive backward |
| **A** | Spin left in place when pressed alone. Curve left when pressed with W or S. |
| **D** | Spin right in place when pressed alone. Curve right when pressed with W or S. |
| **Space** | Stop. Overrides every other key. |
| **E** | Switch between NORMAL and BOOSTER mode. Switches at most once every 0.5 s while held. |
| **Q** | Quit. Sends a stop command and closes the cockpit. |

When no keys are pressed, the cockpit sends a stop command every frame, so letting go of the keys stops the robot. If W and S are both held, W wins. If A and D are both held, A wins.

### How a key press becomes a command

The cockpit uses these values in each mode:

| | NORMAL | BOOSTER |
|---|---|---|
| Forward speed `max_forward` | 0.20 | 0.98 |
| Steering `steering_bias` | 0.19 | 0.955 |
| Spin in place (steering + 0.05) | 0.24 | 1.005 |

**Step 1, forward value V:** `+max_forward` with W, `−max_forward` with S, otherwise 0.

**Step 2, turn value T:**

| | with W | with S | alone |
|---|---|---|---|
| **A** | `+steering` | `−steering` | `+(steering + 0.05)` |
| **D** | `−steering` | `+steering` | `−(steering + 0.05)` |

The turn sign flips when reversing, so S + A reverses toward the left, like reversing a car with the steering wheel turned left.

**Step 3, mix:** `Left = V − T` and `Right = V + T`.

**Step 4, right-turn compensation:** when D is held together with W or S, `Right × 1.55`.

**Step 5, left inversion:** `Left = −Left`, to match the left motor wiring.

**Step 6, send:** `L:<Left>,R:<Right>` with three decimals.

**On the Arduino:** motor power is `|value| × 600`, and the left side is also multiplied by 0.90. Power is capped at 255.

### What actually gets sent (NORMAL mode)

| Keys | Command sent | Left power (0–255) | Right power (0–255) | What the robot does |
|---|---|---|---|---|
| none / Space | `L:-0.000,R:0.000` | 0 | 0 | Stops |
| W | `L:-0.200,R:0.200` | 107 | 120 | Drives forward |
| S | `L:0.200,R:-0.200` | 107 | 120 | Drives backward |
| A | `L:0.240,R:0.240` | 129 | 144 | Spins left in place (left wheels back, right wheels forward) |
| D | `L:-0.240,R:-0.240` | 129 | 144 | Spins right in place |
| W + A | `L:-0.010,R:0.390` | 5 | 233 | Curves forward-left |
| W + D | `L:-0.390,R:0.016` | 210 | 9 | Curves forward-right |
| S + A | `L:0.010,R:-0.390` | 5 | 233 | Reverses, curving left |
| S + D | `L:0.390,R:-0.016` | 210 | 9 | Reverses, curving right |

`-0.000` is how Python prints a negative zero. The Arduino treats it as 0.

So NORMAL forward runs the motors at about 42% (left) and 47% (right) of full power.

### BOOSTER mode

Power hits the 255 cap once the right value passes about 0.43, or the left value passes about 0.47. As a result, BOOSTER driving, spinning, and the outer side of a curve all run at **full power**.

| Keys | Command sent | Left power | Right power |
|---|---|---|---|
| W | `L:-0.980,R:0.980` | 255 | 255 |
| A | `L:1.005,R:1.005` | 255 | 255 |
| W + A | `L:-0.025,R:1.935` | 13 | 255 |
| W + D | `L:-1.935,R:0.039` | 255 | 23 |

---

## 5. Fine-tuned control parameters

These values were fine-tuned through test drives on the real robot. Values were adjusted until the robot drove straight, curved evenly left and right, spun reliably in place and stayed controllable in NORMAL mode. For comparison, an earlier cockpit prototype started at 0.15 forward and 0.14 steering in NORMAL with ×1.5 right-turn compensation, and these were raised to the values below.

| Parameter | Value | File | What it controls |
|---|---|---|---|
| `max_forward` (NORMAL) | 0.20 | `laptop_cockpit.py` | Everyday driving speed, about 42–47% motor power after the Arduino scaling. |
| `steering_bias` (NORMAL) | 0.19 | `laptop_cockpit.py` | How sharply A and D bend the path while moving. Because 0.19 is close to 0.20, the inner side nearly stops and the curves are tight. |
| `max_forward` (BOOSTER) | 0.98 | `laptop_cockpit.py` | Full motor power, for ramps and heavy loads. |
| `steering_bias` (BOOSTER) | 0.955 | `laptop_cockpit.py` | Curve sharpness in BOOSTER mode. |
| Spin extra | +0.05 | `laptop_cockpit.py` | Extra power when spinning in place with A or D alone (0.24 in NORMAL). |
| Right-turn compensation | × 1.55 | `laptop_cockpit.py` | Multiplies the right value on D + W and D + S curves, so right curves behave like left curves. |
| `LEFT_TRIM` | 0.90 | `mecanum_serial_driver.ino` | Runs the left motors at 90% so the robot drives straight instead of pulling to one side. |
| Power scale | × 600, max 255 | `mecanum_serial_driver.ino` | Converts cockpit values into motor power (for example, 0.20 becomes 120 on the right side). |
| `MODE_DEBOUNCE` | 0.5 s | `laptop_cockpit.py` | Stops the E key from flickering between modes. |
| JPEG quality | 55 | `robot_server.py` | Smaller video frames for less delay over Wi-Fi. |
| Camera resolution | 640×480 | `robot_server.py` | Video size sent to the laptop. |

The left sign flip in `laptop_cockpit.py` is **not** a tuning value. It matches the motor wiring, so leave it in place.

**Re-tuning tips:**
- Change one value at a time and test on the real robot.
- After changing a cockpit value, restart `laptop_cockpit.py`.
- After changing an Arduino value, upload the sketch again ([Part 1](#part-1-upload-the-arduino-code-once)).

---

## 6. How to run it

### Words you will see

- **Terminal:** a window where you type commands instead of clicking. On Windows, press the **Windows key**, type **Terminal** (or **PowerShell**) and press **Enter**.
- **SSH:** a way to open a terminal on another computer, here the Raspberry Pi, over the network.
- **Headless:** the Pi on the robot has no screen or keyboard, so you control it from the laptop through SSH.
- **IP address:** the Pi's address on the network, for example `172.17.7.177`.
- **VS Code Remote-SSH:** an add-on that lets VS Code on your laptop open files and terminals on the Pi as if they were on the laptop.

In the commands below, replace `<pi-user>` with the Pi's username and `<PI_IP>` with the Pi's IP address. Type the commands without the `<` `>` brackets.

### Folder names and locations

The commands in this guide assume the project folder is named `GIST_Robots_Delivery_Project`. On the Pi, it sits in the user's home folder (`~`, which is `/home/<pi-user>`). On the laptop, it can be anywhere, for example on the Desktop.

The scripts themselves don't care where they live, but the commands do. `python3 robot_server.py` and `python laptop_cockpit.py` only work when the terminal is **inside the folder that holds the script**. If you use a different folder name or location, do one of these:

- Replace `GIST_Robots_Delivery_Project` with your own folder name or path everywhere it appears in the commands: `mkdir`, `scp`, `cd`, and the folder you open in VS Code.
- Or move into your folder with `cd` before running the script:
  ```
  cd ~/my_robot_folder                          # on the Pi
  cd C:\Users\<you>\Desktop\my_robot_folder     # on the Windows laptop
  ```
  If the path contains spaces, put it in quotes, for example `cd "C:\Users\<you>\Desktop\My Robot"`.

To check where you are, `pwd` shows the current folder and `ls` lists the files in it. Both work on the Pi and in Windows PowerShell. Make sure you can see the script's name in the list before you run it.

### What you need

- **The robot:** Raspberry Pi and Arduino connected by USB, the camera plugged into the Pi and the motor battery charged.
- **A laptop:** the cockpit was built and tested on Windows.
- **A Wi-Fi network** that both the laptop and the Pi can join.
- **The Pi already set up** with Raspberry Pi OS, SSH enabled and Wi-Fi configured. You can set all of this in **Raspberry Pi Imager** when preparing the SD card ("Edit settings" lets you set the username, password and Wi-Fi, and enable SSH). You need that **username and password**.

### Part 1: Upload the Arduino code (once)

You only repeat this part if you change `mecanum_serial_driver.ino`.

1. Install **Arduino IDE 2** from <https://www.arduino.cc/en/software>.
2. Unplug the Arduino from the Pi and plug it into the laptop with its USB cable.
3. In Arduino IDE, choose **File → Open…** and open `GIST_Robots_Delivery_Project/mecanum_serial_driver/mecanum_serial_driver.ino`. The four library files also open as extra tabs, which is correct. Nothing else needs to be installed. Keep the folder name `mecanum_serial_driver` identical to the `.ino` file name, because Arduino IDE requires a sketch to sit in a folder with the same name. If you rename one, rename the other.
4. In the board selector at the top, or under **Tools → Board** and **Tools → Port**, pick your board model (for example, Arduino Uno) and the port that appeared when you plugged it in (for example, `COM3`).
5. Click **Upload** (the round button with an arrow →) and wait for **"Done uploading."**
6. Unplug the Arduino from the laptop and plug it back into the Pi. The program stays on the Arduino even when it loses power.

### Part 2: Prepare the laptop (once)

1. Install **Python 3** from <https://www.python.org/downloads/>. On the first installer screen, tick **"Add python.exe to PATH"**.
2. Open a Terminal and run:
   ```
   pip install opencv-python numpy keyboard
   ```
   If Windows says `pip` is not recognized, run `py -m pip install opencv-python numpy keyboard` instead.
3. Install **VS Code** from <https://code.visualstudio.com/>.
4. In VS Code, click the **Extensions** icon on the left sidebar (four squares) or press **Ctrl+Shift+X**. Search for **Remote - SSH** (publisher: Microsoft) and click **Install**.

### Part 3: Connect to the Pi through SSH (every session)

This is the headless step. You open a terminal on the robot's Pi from the laptop, without connecting a screen to the Pi. It is the quickest way to check that the Pi is on, that you have the right IP and that the Arduino and camera are detected.

1. **Power on the robot** and wait about a minute for the Pi to start. Make sure the laptop is on the **same Wi-Fi network** as the Pi.
2. **Find the Pi's IP address.** The IP can change between networks or days, which is why `laptop_cockpit.py` has an older IP commented out. Use any of these methods:
   - If you use a phone hotspot or can see the router's page, look in its connected-devices list for the Pi (usually named `raspberrypi` or the hostname you chose).
   - In a laptop Terminal, run `ping -4 raspberrypi.local`, replacing `raspberrypi` with your Pi's hostname if you changed it. If it replies, the number shown is the IP. This does not work on every network.
   - Once you are logged in (step 3 below), run `hostname -I`. The first number it prints is the IP.
3. **Log in.** Open a Terminal on the laptop and type:
   ```
   ssh <pi-user>@<PI_IP>
   ```
   For example: `ssh pi@172.17.7.177`
   - The first time, it asks `Are you sure you want to continue connecting (yes/no/[fingerprint])?`. Type `yes` and press Enter.
   - Type the Pi's password and press Enter. **Nothing appears while you type the password.** This is normal.
   - When you see a prompt like `pi@raspberrypi:~ $`, you are on the Pi. Every command you type now runs on the robot.
4. **Quick checks** (optional but useful):
   ```
   hostname -I          # shows the Pi's IP address
   ls /dev/ttyACM*      # should show /dev/ttyACM0, which means the Arduino is detected
   ls /dev/video*       # should show /dev/video0, which means the camera is detected
   ```

### Part 4: Prepare the Pi (first time only)

1. In the SSH terminal from Part 3, install the Python packages the server needs:
   ```
   sudo apt update
   sudo apt install -y python3-opencv python3-serial
   ```
2. Make a folder for the project:
   ```
   mkdir -p ~/GIST_Robots_Delivery_Project
   ```
3. Check that your user may use the Arduino's serial port:
   ```
   groups
   ```
   If `dialout` is **not** in the list, run `sudo usermod -aG dialout $USER`, type `exit`, and log in again with `ssh`.
4. **Copy `robot_server.py` to the Pi.** On the **laptop**, open the project folder in File Explorer, click the address bar, type `powershell` and press **Enter**. A Terminal opens already inside the project folder. Then run:
   ```
   scp robot_server.py <pi-user>@<PI_IP>:~/GIST_Robots_Delivery_Project/
   ```
   Enter the Pi's password when asked.

   *Alternative:* after opening the folder in VS Code (Part 5), you can drag `robot_server.py` from File Explorer into VS Code's file list on the left.

### Part 5: Open the Pi in VS Code and start the robot server (every session)

1. Open VS Code on the laptop.
2. Click the blue **><** button in the **bottom-left corner** ("Open a Remote Window"). Choose **Connect to Host…**, then **+ Add New SSH Host…**. Type `ssh <pi-user>@<PI_IP>` and press Enter, then pick the first settings file it offers. You only need to add the host once, unless the IP changes.
3. Click the **><** button again, choose **Connect to Host…** and pick the Pi's IP. A new VS Code window opens.
4. If asked for the platform, choose **Linux**. Enter the Pi's password in the box at the top of the window.
   - The first connection takes a minute or two while VS Code installs a small helper on the Pi, and the Pi needs internet access for this.
   - When the bottom-left corner shows **SSH: <PI_IP>**, this window is working on the Pi.
5. Choose **File → Open Folder…**, select `/home/<pi-user>/GIST_Robots_Delivery_Project` (or the folder where you put `robot_server.py`) and click **OK**. Enter the password again if asked. If VS Code asks whether you trust the authors, click **Yes**.
6. Open a terminal inside VS Code with **Terminal → New Terminal** (or **Ctrl+`**). This terminal runs on the Pi.
7. Start the server:
   ```
   python3 robot_server.py
   ```
   You should see:
   ```
   Connecting to Arduino...
   ✅ Motor line established!
   🚀 Robot Server Listening on port 8089... Awaiting Laptop Connection...
   ```
8. **Leave this running** and keep the VS Code window open while you drive.

VS Code makes it easy to view and edit files on the Pi, but it is optional. The same command works in the plain SSH terminal from Part 3:

```
cd ~/GIST_Robots_Delivery_Project
python3 robot_server.py
```

### Part 6: Start the cockpit on the laptop and drive (every session)

1. Open `laptop_cockpit.py` on the laptop in any editor (VS Code, Notepad, IDLE). Near the top, find this line:
   ```python
   ROBOT_IP = '172.17.7.177'
   ```
   Replace the number with your Pi's IP and **save**. The line starting with `#` just above it is a comment and is ignored.
2. Open a Terminal inside the project folder (File Explorer → address bar → `powershell` → Enter) and run:
   ```
   python laptop_cockpit.py
   ```
   If `python` is not recognized, use `py laptop_cockpit.py`.
3. You should see `✅ Connected to Robot Live Feed!`, and the cockpit window opens. In VS Code on the Pi side, you should see `✅ Laptop Connected from: ...`.
4. **Drive** with the keys in [Section 4](#controls). You don't need to click the window, because keys are read from anywhere on the laptop.

**Order matters: always start `robot_server.py` on the Pi first, then the cockpit.**

### Part 7: Stopping

1. Press **Q**. The cockpit sends a stop command and closes.
2. The server on the Pi notices that the laptop left, stops the motors, prints `Hardware lines safe and offline.` and exits. If it is still running, click inside the VS Code terminal and press **Ctrl+C**, which also stops the motors.
3. **To drive again,** run `python3 robot_server.py` again on the Pi first, then the cockpit.
4. **To power off,** run this in the Pi terminal:
   ```
   sudo shutdown now
   ```
   Wait about 10 seconds until the Pi's green light stops blinking, then switch off the power. Cutting power without shutting down can damage the Pi's SD card.

---

## 7. Troubleshooting

| Problem | What to check |
|---|---|
| `❌ Arduino Failed: ... could not open port /dev/ttyACM0` | Is the Arduino plugged into the Pi? Run `ls /dev/ttyACM* /dev/ttyUSB*`. If it shows `/dev/ttyUSB0` (common on clone boards), change `SERIAL_PORT` in `robot_server.py`. If the error says *Permission denied*, see Part 4, step 3. Make sure no other program is using the port, such as another copy of the server. |
| `can't open file '...robot_server.py'` (or `laptop_cockpit.py`): `[Errno 2] No such file or directory` | The terminal is not inside the folder that holds the script. Run `pwd` to see where you are and `ls` to list the files, then `cd` into the right folder (see [Folder names and locations](#folder-names-and-locations)). |
| `Address already in use` when starting the server | An old copy is still running. Run `pkill -f robot_server.py`, then start it again. |
| Laptop: *"No connection could be made because the target machine actively refused it"* | The server is not running yet, or `ROBOT_IP` is wrong. Start the server first and check the IP. |
| Laptop is stuck at `Connecting to Robot Cockpit...` or times out | The IP is wrong, the devices are on different networks, or the network blocks device-to-device traffic (common on campus or guest Wi-Fi). Try connecting both the laptop and the Pi to a phone hotspot. |
| Connected, but no video appears | Run `ls /dev/video*` on the Pi. The server quietly skips frames the camera fails to deliver, so no video usually means a camera problem. Because commands are sent once per video frame, the robot also won't receive commands. |
| Video works but the wheels don't move | Is the motor battery on? Does the Pi terminal show `Routing to Wheels: ...`? If not, check the connection. If yes, re-upload the Arduino sketch and check the motor wiring. |
| `ModuleNotFoundError: No module named 'cv2'` (or `keyboard`, `serial`) | Install the packages (Part 2 on the laptop, Part 4 on the Pi). On the Pi, use `apt` as shown. Plain `pip` may refuse with *externally-managed-environment*. |
| Robot pulls to one side on W | Adjust `LEFT_TRIM` in the `.ino` and re-upload. |
| VS Code can't connect to the Pi | First test the plain `ssh` command from Part 3. Check the IP and password. The Pi needs internet access the first time. Very old Pi models (Pi Zero / Pi 1) are not supported by VS Code Remote-SSH, so use the plain SSH terminal instead. |

---

## 8. Good to know

- **Keys are read from the whole laptop, not just the cockpit window.** The `keyboard` library listens globally, so pressing W while typing in another app also drives the robot. Quit the cockpit (Q) before typing elsewhere. The "CLICK HERE TO DRIVE" banner is only a label, and clicking is not required.
- **One command per video frame.** If the video freezes, commands pause too.
- **The Arduino keeps doing the last command** until a new one arrives. The motors stop in these cases:
  - you release all keys or press Space;
  - you press Q;
  - the Pi server shuts down after detecting a disconnect, or you press Ctrl+C on it.

  If Wi-Fi drops silently in the middle of driving, the robot can keep moving until the Pi notices. Keep someone near the robot during tests.
- **One laptop at a time.** The server accepts one connection per run, so restart it for each session.
- **Other operating systems:** the cockpit was tested on Windows. On Linux, the `keyboard` library needs `sudo`. On macOS, it needs accessibility permission.
