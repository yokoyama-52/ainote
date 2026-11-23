#include <Servo.h>

// Wiring: servo signal -> D9, servo power -> suitable external supply,
// and the supply GND must be common with Arduino GND.
constexpr uint8_t SERVO_PIN = 9;

// A larger 90 degree stroke for the tambourine arm. Change these only after
// checking that the mechanism has clearance at both ends of travel.
constexpr int REST_ANGLE = 70;
constexpr int STRIKE_ANGLE = 110;
constexpr unsigned long STRIKE_HOLD_MS = 75;

Servo striker;
char command[8];
uint8_t commandLength = 0;
bool striking = false;
unsigned long strikeStartedAt = 0;

void hit() {
  // Reply immediately: the desktop app treats OK as receipt of the command.
  // Repeated beats refresh the strike hold instead of blocking serial input.
  striker.write(STRIKE_ANGLE);
  striking = true;
  strikeStartedAt = millis();
  Serial.println(F("OK"));
}

void handleCommand() {
  command[commandLength] = '\0';
  if (strcmp(command, "HIT") == 0) {
    hit();
  }
  commandLength = 0;
}

void setup() {
  Serial.begin(115200);
  striker.attach(SERVO_PIN);
  striker.write(REST_ANGLE);
}

void loop() {
  while (Serial.available() > 0) {
    const char received = static_cast<char>(Serial.read());
    if (received == '\n') {
      handleCommand();
    } else if (received != '\r' && commandLength < sizeof(command) - 1) {
      command[commandLength++] = received;
    } else if (commandLength >= sizeof(command) - 1) {
      commandLength = 0;  // Discard an overlong malformed command.
    }
  }

  if (striking && millis() - strikeStartedAt >= STRIKE_HOLD_MS) {
    striker.write(REST_ANGLE);
    striking = false;
  }
}
