#include <Servo.h>

Servo left, right;
byte ladd = 70, radd = 70;

// Protocol state machine tracking
enum ParserState {
    STATE_NORMAL,
    STATE_EXPECTING_LEFT_OFFSET,
    STATE_EXPECTING_RIGHT_OFFSET
};

ParserState currentState = STATE_NORMAL;

void setup() {
  left.attach(6);
  right.attach(9);

  left.write(ladd);
  right.write(radd);

  Serial.begin(9600);
  Serial.println("belt servos: connected");
}

void loop() {
  while (Serial.available() > 0) {
    byte received = Serial.read();

    switch (currentState) {
      case STATE_EXPECTING_LEFT_OFFSET:
        ladd = received;
        left.write(ladd); 
        currentState = STATE_NORMAL;
        break;

      case STATE_EXPECTING_RIGHT_OFFSET:
        radd = received;
        right.write(radd);
        currentState = STATE_NORMAL;
        break;

      case STATE_NORMAL:
      default:
        if (received == 0) {
          // Opcode 0: Next byte is left offset calibration value
          currentState = STATE_EXPECTING_LEFT_OFFSET;
        } 
        else if (received == 1) {
          // Opcode 1: Next byte is right offset calibration value
          currentState = STATE_EXPECTING_RIGHT_OFFSET;
        } 
        else {
          // Positional data payload (Values >= 2)
          if (received & 1) {
            // LSB is 1 -> Right Channel
            right.write((received & 127) + radd);
          } else {
            // LSB is 0 -> Left Channel
            left.write((received & 127) + ladd);
          }
        }
        break;
    }
  }
}