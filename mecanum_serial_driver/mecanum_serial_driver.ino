#include <Wire.h>
#include "QGPMaker_MotorShield.h"

#define BAUDRATE 115200

// Initialize the true factory motor shield structure
QGPMaker_MotorShield AFMS = QGPMaker_MotorShield();

// Exact physical mapping from your working factory file
QGPMaker_DCMotor *DCMotor_1 = AFMS.getMotor(1); // Front Left
QGPMaker_DCMotor *DCMotor_2 = AFMS.getMotor(2); // Rear Left
QGPMaker_DCMotor *DCMotor_3 = AFMS.getMotor(3); // Front Right
QGPMaker_DCMotor *DCMotor_4 = AFMS.getMotor(4); // Rear Right

// Global stream packet matrix array
String inputBuffer = "";
float LEFT_TRIM = 0.90; 

void setup() {
  Serial.begin(BAUDRATE);
  
  // Initialize the shield chip at 50Hz frequency
  AFMS.begin(50);
  
  // Safe stop on initialization
  stopMoving();
}

void loop() {
  // Read clean serial bytes instantly without blocking execution loops
  while (Serial.available() > 0) {
    char inChar = (char)Serial.read();
    
    // If we hit the end of a command packet line, parse it instantly!
    if (inChar == '\n') {
      if (inputBuffer.indexOf("L:") >= 0 && inputBuffer.indexOf(",R:") >= 0) {
        int l_index = inputBuffer.indexOf("L:") + 2;
        int r_index = inputBuffer.indexOf(",R:");
        float left_speed = inputBuffer.substring(l_index, r_index).toFloat();
        float right_speed = inputBuffer.substring(r_index + 3).toFloat();
        
        controlMotors(left_speed, right_speed);
      }
      inputBuffer = ""; // Flush the buffer for the next incoming packet
    } else {
      inputBuffer += inChar; // Append byte to message matrix array
    }
  }
}

void controlMotors(float left, float right) {
  // Map target velocity values to native board speed scale (0 to 255)
  // We apply the LEFT_TRIM directly to the raw float input first
  int left_pwm  = constrain(abs(left * LEFT_TRIM) * 600.0, 0, 255);
  int right_pwm = constrain(abs(right) * 600.0, 0, 255);

  // --- LEFT AXLE MOTORS (1 & 2) ---
  // Because the laptop code flips the left target internally, a positive 
  // left value here means the chassis needs the left wheels to push FORWARD.
  if (left >= 0.0) {
    DCMotor_1->run(FORWARD);
    DCMotor_2->run(FORWARD);
  } else {
    DCMotor_1->run(BACKWARD);
    DCMotor_2->run(BACKWARD);
  }
  DCMotor_1->setSpeed(left_pwm);
  DCMotor_2->setSpeed(left_pwm);

  // --- RIGHT AXLE MOTORS (3 & 4) ---
  if (right >= 0.0) {
    DCMotor_3->run(FORWARD);
    DCMotor_4->run(FORWARD);
  } else {
    DCMotor_3->run(BACKWARD);
    DCMotor_4->run(BACKWARD);
  }
  DCMotor_3->setSpeed(right_pwm);
  DCMotor_4->setSpeed(right_pwm);
}

void stopMoving() {
  DCMotor_1->setSpeed(0); DCMotor_1->run(RELEASE);
  DCMotor_2->setSpeed(0); DCMotor_2->run(RELEASE);
  DCMotor_3->setSpeed(0); DCMotor_3->run(RELEASE);
  DCMotor_4->setSpeed(0); DCMotor_4->run(RELEASE);
}
