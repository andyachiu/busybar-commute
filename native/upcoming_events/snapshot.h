#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define EVENTS_MAX 20
#define SNAPSHOT_MAX (20 + EVENTS_MAX * 272)
typedef struct {
  char title[80];
  char venue[48];
  char timing[48];
  char departure[80];
  char kind[16];
} EventRow;
typedef struct {
  uint32_t fetched;
  uint32_t count;
  EventRow rows[EVENTS_MAX];
} EventSnapshot;
bool snapshot_decode(const uint8_t *bytes, size_t size, EventSnapshot *output);
