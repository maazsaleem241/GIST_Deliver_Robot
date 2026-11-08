#!/usr/bin/env python3
import cv2
import socket
import pickle
import struct
import serial
import time
import sys
import threading

# --- CONFIGURATION ---
SERIAL_PORT = '/dev/ttyACM0'
BAUD_RATE = 115200
HOST_IP = '0.0.0.0'
PORT = 8089

# 1. Connect to Arduino
print("Connecting to Arduino...")
try:
    arduino = serial.Serial(port=SERIAL_PORT, baudrate=BAUD_RATE, timeout=0.1)
    time.sleep(2)
    print("✅ Motor line established!")
except Exception as e:
    print(f"❌ Arduino Failed: {e}")
    sys.exit(1)

# 2. Setup Camera (Upgraded to Native High Resolution Layout)
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)  # Native Crisp Matrix Baseline
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

# 3. Setup Network Socket
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_socket.bind((HOST_IP, PORT))
server_socket.listen(1)
print(f"🚀 Robot Server Listening on port {PORT}... Awaiting Laptop Connection...")

def command_listener_thread(conn):
    """Runs on an independent loop to process driving keys instantly."""
    print("Motor command listener thread spawned.")
    while True:
        try:
            packet = conn.recv(1024).decode('utf-8')
            if not packet:
                break
            if packet.startswith("L:"):
                arduino.write(packet.encode('utf-8'))
                print(f"Routing to Wheels: {packet.strip()}   ", end="\r")
        except Exception:
            break
    print("\n Motor command listener thread closed.")

try:
    conn, addr = server_socket.accept()
    print(f"✅ Laptop Connected from: {addr}")
    
    # Fire up parallel command processing thread
    cmd_thread = threading.Thread(target=command_listener_thread, args=(conn,), daemon=True)
    cmd_thread.start()

    while True:
        ret, frame = cap.read()
        if not ret:
            continue
        
        # Optimize throughput: Quality 55 significantly lowers payload latency over Wi-Fi
        _, encoded_frame = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 55])
        data = pickle.dumps(encoded_frame)
        
        try:
            # Send payload header + packet matrix frame
            conn.sendall(struct.pack("Q", len(data)) + data)
        except Exception as e:
            print(f"\n!!! Client disconnected while sending frames: {e}")
            break

except Exception as e:
    print(f"\nUnexpected Error: {e}")

finally:
    print("\nShutting down stream down safely...")
    try:
        arduino.write("L:0.0,R:0.0\n".encode('utf-8'))
        arduino.close()
    except:
        pass
    cap.release()
    server_socket.close()
    print("Hardware lines safe and offline.")
