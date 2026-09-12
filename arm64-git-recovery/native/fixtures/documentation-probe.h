/** @file documentation-probe.h
 *  Public documentation-generation control; never compiled or shipped.
 */

/** Values carried by the documentation control. */
typedef struct documentation_probe {
    unsigned int count; /**< Number of values. */
} documentation_probe;

/** Return the documented count.
 *  @param value The control value.
 *  @return The count carried by value.
 */
unsigned int documentation_probe_count(const documentation_probe *value);
