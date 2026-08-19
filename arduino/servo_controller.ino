#include <Servo.h>

// DS5180SG servo specs (180° mode):
//   Pulse range: 500-2500us, Neutral: 1500us, Dead band: 3us
//   1° = 2000us / 180 = 11.11us
//
// 72° = servo arm horizontal = belts maximally relaxed = home position.
//   72° = 500 + 72 * 11.11 = 1300us
//
// All positional data is relative to this base (0 = relaxed = 72°).

#define SERVO_BASE_DEG 72
#define SERVO_MIN_US   500
#define SERVO_MAX_US   2500
#define SERVO_RANGE    180

// Convert degree to microseconds for DS5180SG
#define DEG_TO_US(deg) (SERVO_MIN_US + (long)(deg) * (SERVO_MAX_US - SERVO_MIN_US) / SERVO_RANGE)
#define SERVO_BASE_US  DEG_TO_US(SERVO_BASE_DEG)

// Protocol v2: sync-based framing, no bit-packing
#define SYNC_BYTE    253
#define OP_LEFT_OFF  254
#define OP_RIGHT_OFF 255

Servo left, right;
byte ladd = 0, radd = 0;

enum ParserState {
    STATE_WAIT_OPCODE,         // expecting sync/opcode byte
    STATE_WAIT_LEFT,           // got sync, expecting left tension
    STATE_WAIT_RIGHT,          // got left, expecting right tension
    STATE_EXPECT_LEFT_OFFSET,  // got 254, expecting left offset value
    STATE_EXPECT_RIGHT_OFFSET  // got 255, expecting right offset value
};

ParserState currentState = STATE_WAIT_OPCODE;

void setup() {
  left.attach(6);
  right.attach(9);

  // Start at home position (belts relaxed): 72° = 1300us
  left.writeMicroseconds(SERVO_BASE_US);
  right.writeMicroseconds(SERVO_BASE_US);

  Serial.begin(9600);
  Serial.println("belt servos: connected");
}

void loop() {
  while (Serial.available() > 0) {
    byte received = Serial.read();

    switch (currentState) {
      case STATE_WAIT_LEFT:
        // Left tension (0-252): 0 = relaxed (72°), higher = more pull
        // Max: 72 + 252 = 324° but servo only goes to 180°, constrain handles it
        left.writeMicroseconds(constrain(DEG_TO_US(SERVO_BASE_DEG + received + ladd), SERVO_MIN_US, SERVO_MAX_US));
        currentState = STATE_WAIT_RIGHT;
        break;

      case STATE_WAIT_RIGHT:
        // Right tension (0-252): 0 = relaxed (72°), higher = more pull
        right.writeMicroseconds(constrain(DEG_TO_US(SERVO_BASE_DEG + received + radd), SERVO_MIN_US, SERVO_MAX_US));
        currentState = STATE_WAIT_OPCODE;
        break;

      case STATE_EXPECT_LEFT_OFFSET:
        ladd = received;
        left.writeMicroseconds(constrain(DEG_TO_US(SERVO_BASE_DEG + ladd), SERVO_MIN_US, SERVO_MAX_US));
        currentState = STATE_WAIT_OPCODE;
        break;

      case STATE_EXPECT_RIGHT_OFFSET:
        radd = received;
        right.writeMicroseconds(constrain(DEG_TO_US(SERVO_BASE_DEG + radd), SERVO_MIN_US, SERVO_MAX_US));
        currentState = STATE_WAIT_OPCODE;
        break;

      case STATE_WAIT_OPCODE:
      default:
        if (received == SYNC_BYTE) {
          currentState = STATE_WAIT_LEFT;
        } else if (received == OP_LEFT_OFF) {
          currentState = STATE_EXPECT_LEFT_OFFSET;
        } else if (received == OP_RIGHT_OFF) {
          currentState = STATE_EXPECT_RIGHT_OFFSET;
        }
        // Ignore any other byte (stays in WAIT_OPCODE)
        break;
    }
  }
}