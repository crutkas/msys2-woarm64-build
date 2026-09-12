STATIC_LIBEDIT_OBJECTS := $(patsubst %.lo,$(STATIC_LIBEDIT_DIR)/%.o,$(libedit_la_OBJECTS))

$(STATIC_LIBEDIT_DIR)/%.o: $(srcdir)/%.c $(BUILT_SOURCES)
	$(COMPILE) -DNCURSES_STATIC -c -o $@ $<

$(STATIC_LIBEDIT_DIR)/libedit.a: $(STATIC_LIBEDIT_OBJECTS)
	$(AR) $(STATIC_LIBEDIT_AR_FLAGS) $@ $?
	$(RANLIB) $@

.PHONY: chain-static-libedit
chain-static-libedit: $(STATIC_LIBEDIT_DIR)/libedit.a
