#include "snapshot.h"
#include <string.h>
_Static_assert(sizeof(EventRow) == 272, "Wire record layout changed");
static uint32_t read32(const uint8_t *p) {
  return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) |
         ((uint32_t)p[3] << 24);
}
bool snapshot_decode(const uint8_t *bytes, size_t size, EventSnapshot *output) {
  if (size < 20 || size > SNAPSHOT_MAX || memcmp(bytes, "CBAR0001", 8))
    return false;
  uint32_t count = read32(bytes + 16);
  if (count > EVENTS_MAX || size != 20 + count * 272)
    return false;
  uint32_t crc = 0xffffffff;
  for (size_t i = 12; i < size; ++i) {
    crc ^= bytes[i];
    for (unsigned bit = 0; bit < 8; ++bit)
      crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1)));
  }
  if ((crc ^ 0xffffffff) != read32(bytes + 8))
    return false;
  const size_t widths[] = {80, 48, 48, 80, 16};
  for (size_t i = 20; i < size;) {
    for (unsigned f = 0; f < 5; ++f) {
      bool ended = false;
      for (size_t j = 0; j < widths[f]; ++j) {
        uint8_t c = bytes[i + j];
        if (c == 0)
          ended = true;
        else if (ended || c < 32 || c > 126)
          return false;
      }
      if (!ended)
        return false;
      i += widths[f];
    }
  }
  /* Commit only after all validation; invalid uploads leave the old snapshot
   * intact. */
  output->fetched = read32(bytes + 12);
  output->count = count;
  memcpy(output->rows, bytes + 20, count * sizeof(EventRow));
  return true;
}
