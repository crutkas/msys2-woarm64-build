#include <windows.h>
#include <string.h>

typedef VOID (NTAPI *unwind_function)(
    PVOID, PVOID, PEXCEPTION_RECORD, PVOID, PCONTEXT, PUNWIND_HISTORY_TABLE);

extern unwind_function __real___imp_RtlUnwindEx;

_Static_assert(sizeof(CONTEXT) == 912, "Expected qualified ARM64 CONTEXT");

static void NTAPI private_unwind_context(
    PVOID frame, PVOID target, PEXCEPTION_RECORD exception, PVOID value,
    PCONTEXT incoming, PUNWIND_HISTORY_TABLE history)
{
    /* RtlUnwindEx writes its scratch context; never give it the saved
       KiUserExceptionDispatcher context that phase 2 still needs to restore. */
    _Alignas(16) CONTEXT scratch;
    memcpy(&scratch, incoming, sizeof(scratch));
    __real___imp_RtlUnwindEx(frame, target, exception, value, &scratch, history);
}

unwind_function __wrap___imp_RtlUnwindEx = private_unwind_context;
