extern long frame_sink(void *);
extern long frame_sink_many(void *, long, long, long, long, long, long, long, long, long);

long unwind_large_dynamic(unsigned long count)
{
  char fixed[8192];
  char dynamic[count + 1];
  fixed[0] = 17;
  dynamic[0] = 23;
  return frame_sink_many(fixed, 1, 2, 3, 4, 5, 6, 7, 8, 9) + frame_sink(dynamic);
}
