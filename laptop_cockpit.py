#!/usr/bin/env python3
import cv2
import socket
import struct
import pickle
import numpy as np
import time
import keyboard  # Swapped from Pygame to fix the window click focus issue!

# --- CONFIGURATION ---
#ROBOT_IP = '10.222.18.158'  # Utilizing clean mDNS resolving!
ROBOT_IP = '172.17.7.177'
PORT = 8089

client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
print(f"Connecting to Robot Cockpit at {ROBOT_IP}...")
client_socket.connect((ROBOT_IP, PORT))
print("✅ Connected to Robot Live Feed!")

# Set window behavior to normal so it can adapt dynamically
cv2.namedWindow("LAPTOP TELEOP COCKPIT", cv2.WINDOW_NORMAL)
cv2.resizeWindow("LAPTOP TELEOP COCKPIT", 1280, 720)

data = b""
payload_size = struct.calcsize("Q")

# State tracking variables for fluid movement
base_motion = "IDLE"      # Can be: "FORWARD", "BACKWARD", "IDLE"
turn_direction = "NONE"   # Can be: "LEFT", "RIGHT", "NONE"
active_ui_key = "NONE"    # Used strictly to light up the UI dashboard panels
drive_mode = "NORMAL"     # Can toggle between: "NORMAL" and "BOOSTER"

# Debounce tracker for mode switching
last_mode_toggle = 0.0
MODE_DEBOUNCE = 0.5

def draw_hd_control_panel(width, height, active_cmd, current_mode):
    """Generates an HD vector control dashboard dynamically matching the display height."""
    panel = np.ones((height, width, 3), dtype=np.uint8) * 22
    
    scale_factor = height / 720.0
    font_scale = max(0.4, 0.5 * scale_factor)
    
    # 🎯 Interactive Focus Notice Banner
    cv2.rectangle(panel, (int(10*scale_factor), int(10*scale_factor)), (width - int(10*scale_factor), int(50*scale_factor)), (0, 165, 255), 1)
    cv2.putText(panel, "CLICK HERE TO DRIVE", (int(25*scale_factor), int(35*scale_factor)), 
                cv2.FONT_HERSHEY_SIMPLEX, font_scale * 0.9, (0, 165, 255), 1, cv2.LINE_AA)

    cv2.putText(panel, "COCKPIT CONTROL", (int(20*scale_factor), int(90*scale_factor)), 
                cv2.FONT_HERSHEY_SIMPLEX, font_scale * 1.1, (200, 200, 200), 1, cv2.LINE_AA)
    cv2.line(panel, (int(15*scale_factor), int(105*scale_factor)), (width - int(15*scale_factor), int(105*scale_factor)), (60, 60, 60), 1)

    mid_x = width // 2
    key_w, key_h = int(60 * scale_factor), int(60 * scale_factor)
    gap = int(15 * scale_factor)

    keys = {
        'W': (mid_x, int(170*scale_factor), key_w, key_h),
        'A': (mid_x - key_w - gap, int(170*scale_factor) + key_h + gap, key_w, key_h),
        'S': (mid_x, int(170*scale_factor) + key_h + gap, key_w, key_h),
        'D': (mid_x + key_w + gap, int(170*scale_factor) + key_h + gap, key_w, key_h),
        'SPACE': (mid_x, int(170*scale_factor) + 2*(key_h + gap), int(200*scale_factor), int(40*scale_factor))
    }

    for key_name, (cx, cy, w, h) in keys.items():
        p1 = (cx - w // 2, cy - h // 2)
        p2 = (cx + w // 2, cy + h // 2)
        
        if active_cmd == key_name:
            bg_color = (0, 230, 0)       # Neon green
            text_color = (0, 0, 0)       # Deep black text
            thickness = -1
        else:
            bg_color = (80, 80, 80)      # Clean gray frame
            text_color = (200, 200, 200) # Bright text
            thickness = 2

        cv2.rectangle(panel, p1, p2, bg_color, thickness)
        
        label = 'STOP' if key_name == 'SPACE' else key_name
        text_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)[0]
        text_offset = (cx - text_size[0] // 2, cy + text_size[1] // 2)
        
        cv2.putText(panel, label, text_offset, cv2.FONT_HERSHEY_SIMPLEX, font_scale, text_color, 1, cv2.LINE_AA)

    # Transmission Mode Badge Layout
    mode_color = (0, 165, 255) if current_mode == "BOOSTER" else (255, 150, 0)
    cv2.rectangle(panel, (int(20*scale_factor), int(420*scale_factor)), (width - int(20*scale_factor), int(470*scale_factor)), mode_color, -1)
    
    mode_label = f"MODE: {current_mode} (Press E)"
    m_size = cv2.getTextSize(mode_label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)[0]
    cv2.putText(panel, mode_label, (width // 2 - m_size[0] // 2, int(450*scale_factor)), 
                cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 0), 2, cv2.LINE_AA)

    cv2.line(panel, (int(15*scale_factor), height - int(60*scale_factor)), (width - int(15*scale_factor), height - int(60*scale_factor)), (60, 60, 60), 1)
    cv2.putText(panel, f"VEC: {active_cmd}", (int(20*scale_factor), height - int(30*scale_factor)), 
                cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 255, 255), 1, cv2.LINE_AA)
    return panel

print("\n🚀 Single-Window input mapping engine online.")
print("📺 Click anywhere inside the main 'LAPTOP TELEOP COCKPIT' window to drive!")
print("⚙️ Press 'E' to toggle profiles. Press 'Q' to exit.")
print("--------------------------------------------------")

try:
    while True:
        # 1. Retrieve & Unpack Video Payload
        while len(data) < payload_size:
            packet = client_socket.recv(4096)
            if not packet: raise Exception("Disconnected")
            data += packet
        
        packed_msg_size = data[:payload_size]
        data = data[payload_size:]
        msg_size = struct.unpack("Q", packed_msg_size)[0]
        
        while len(data) < msg_size:
            data += client_socket.recv(4096)
            
        frame_data = data[:msg_size]
        data = data[msg_size:]
        
        encoded_frame = pickle.loads(frame_data)
        frame = cv2.imdecode(encoded_frame, cv2.IMREAD_COLOR)

        # 2. Key Processing Event Capture (POLLING ASYNCHRONOUSLY WITHOUT CLUNKY GHOST WINDOWS)
        current_time = time.time()

        # Emergency shutdown check
        if keyboard.is_pressed('q'):
            print("\n🛑 Emergency shutdown requested.")
            client_socket.sendall("L:0.000,R:0.000\n".encode('utf-8'))
            break

        # Mode toggle handler with structural debounce
        if keyboard.is_pressed('e'):
            if current_time - last_mode_toggle > MODE_DEBOUNCE:
                drive_mode = "BOOSTER" if drive_mode == "NORMAL" else "NORMAL"
                last_mode_toggle = current_time
                print(f"\n⚙️ Drivetrain engine profile changed to: {drive_mode}")

        # Reset active cycle baseline states
        base_motion = "IDLE"
        turn_direction = "NONE"
        active_ui_key = "NONE"

        # Evaluate keyboard physical state maps directly
        if keyboard.is_pressed('w'):
            base_motion = "FORWARD"
            active_ui_key = "W"
        elif keyboard.is_pressed('s'):
            base_motion = "BACKWARD"
            active_ui_key = "S"

        if keyboard.is_pressed('a'):
            turn_direction = "LEFT"
            if base_motion == "IDLE":
                active_ui_key = "A"
        elif keyboard.is_pressed('d'):
            turn_direction = "RIGHT"
            if base_motion == "IDLE":
                active_ui_key = "D"

        if keyboard.is_pressed('space'):
            base_motion = "IDLE"
            turn_direction = "NONE"
            active_ui_key = "SPACE"

        # 🏎️ VELOCITY CONFIGURATION
        forward_vel = 0.0
        turn_vel = 0.0
        log_msg = "Idling"

        if drive_mode == "BOOSTER":
            max_forward = 0.98 
            steering_bias = 0.955
        else:
            max_forward = 0.20    
            steering_bias = 0.19 

        # A. Apply baseline speeds
        if base_motion == "FORWARD":
            forward_vel = max_forward
            log_msg = f"Driving Forward ({drive_mode})"
        elif base_motion == "BACKWARD":
            forward_vel = -max_forward
            log_msg = f"Driving Backward ({drive_mode})"

        # B. Apply context-aware vector steering math
        if turn_direction == "LEFT":
            if base_motion == "BACKWARD":
                turn_vel = -steering_bias
                log_msg = "Blending Curve Backward-Left"
            elif base_motion == "FORWARD":
                turn_vel = steering_bias
                log_msg = "Blending Curve Forward-Left"
            else:
                turn_vel = steering_bias + 0.05
                log_msg = "Spinning Left Stationary"
                
        elif turn_direction == "RIGHT":
            if base_motion == "BACKWARD":
                turn_vel = steering_bias
                log_msg = "Blending Curve Backward-Right"
            elif base_motion == "FORWARD":
                turn_vel = -steering_bias
                log_msg = "Blending Curve Forward-Right"
            else:
                turn_vel = -(steering_bias + 0.05)
                log_msg = "Spinning Right Stationary"

        # Calculate blended components
        left_target = forward_vel - turn_vel
        right_target = forward_vel + turn_vel

        # Software asymmetry balance compensation (right turn correction factor @ 1.5)
        if turn_direction == "RIGHT" and base_motion != "IDLE":
            right_target *= 1.55

        # Invert left channel to match local platform physical wiring requirements
        left_target = -left_target

        # Transmit active streaming telemetry vector matrix packets
        motor_packet = f"L:{left_target:.3f},R:{right_target:.3f}\n"
        try:
            client_socket.sendall(motor_packet.encode('utf-8'))
            print(f"Vector -> {log_msg} | Packets: {motor_packet.strip()}     ", end="\r")
        except Exception as e:
            print(f"\nFailed to transmit control matrix: {e}")
            break

        # 3. Handle Responsive Window Scaling
        window_rect = cv2.getWindowImageRect("LAPTOP TELEOP COCKPIT")
        win_w, win_h = window_rect[2], window_rect[3]

        if win_w <= 0 or win_h <= 0:
            win_w, win_h = 1280, 720

        video_target_w = int(win_w * 0.75)
        ui_target_w = win_w - video_target_w

        frame_resized = cv2.resize(frame, (video_target_w, win_h), interpolation=cv2.INTER_LINEAR)
        ui_panel_hd = draw_hd_control_panel(ui_target_w, win_h, active_ui_key, drive_mode)
        dashboard_panel = np.hstack((frame_resized, ui_panel_hd))

        cv2.imshow("LAPTOP TELEOP COCKPIT", dashboard_panel)
        
        # Check if user clicked close on the window frame natively
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

except Exception as e:
    print(f"\nConnection closed: {e}")

finally:
    print("\nClosing down terminal interface safety systems...")
    try:
        client_socket.sendall("L:0.000,R:0.000\n".encode('utf-8'))
    except:
        pass
    client_socket.close()
    cv2.destroyAllWindows()