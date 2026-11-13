#include <stdint.h>
/* A real dynamically loaded, FSW-resident executable dependency. */
uint64_t flight_square_sum(unsigned int count)
{
    uint64_t result = 0;
    for (unsigned int i = 0; i < count; ++i) {
        result += (uint64_t)i * i;
    }
    return result;
}
