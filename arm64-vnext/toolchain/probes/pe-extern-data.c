extern unsigned long long external_value;
extern unsigned long long external_array[];
extern unsigned long long weak_value __attribute__((weak));
extern long external_function(long);
static unsigned long long local_value;

unsigned long long read_external(void) { return external_value; }
void write_external(unsigned long long value) { external_value = value; }
unsigned long long *address_external(void) { return &external_value; }
unsigned long long *offset_external(void) { return &external_array[3]; }
unsigned long long *large_offset_external(void) { return &external_array[0x20000000]; }
unsigned long long *negative_offset_external(void) { return external_array - 3; }
unsigned long long read_weak(void) { return weak_value; }
unsigned long long *address_local(void) { return &local_value; }
long call_external(long value) { return external_function(value); }
