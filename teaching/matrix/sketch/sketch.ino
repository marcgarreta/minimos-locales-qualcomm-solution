// Kangaroo Matrix: draws whatever frame the Python side has ready.
// Python builds every picture; the sketch only asks for it (Bridge.call("frame"))
// and copies the 104 characters '0'..'7' (8 rows x 13 columns) to the LED matrix.
#include <Arduino_RouterBridge.h>
#include <Arduino_LED_Matrix.h>

Arduino_LED_Matrix matrix;

const int FRAME_SIZE = 8 * 13;
uint8_t frame[FRAME_SIZE] = {0};

void setup() {
  matrix.begin();
  matrix.setGrayscaleBits(3);   // brightness 0..7
  matrix.clear();
  Bridge.begin();
}

void loop() {
  String s;
  if (Bridge.call("frame").result(s) && s.length() >= FRAME_SIZE) {
    for (int i = 0; i < FRAME_SIZE; i++) {
      char c = s[i];
      frame[i] = (c >= '0' && c <= '7') ? c - '0' : 0;
    }
    matrix.draw(frame);
  }
  delay(40);
}
