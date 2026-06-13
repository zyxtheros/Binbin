#include <Arduino.h>

// put function declarations here:
//int myFunction(int, int);
int  myLED = 23;

void setup() {
  // put your setup code here, to run once:
  //int result = myFunction(2, 3);
  pinMode(myLED, OUTPUT);
}

void loop() {
  // put your main code here, to run repeatedly:
  digitalWrite(myLED, HIGH);
  delay(1000);
  digitalWrite(myLED, LOW);
  delay(1000);
}

// put function definitions here:
//int myFunction(int x, int y) {
//  return x + y;
//}