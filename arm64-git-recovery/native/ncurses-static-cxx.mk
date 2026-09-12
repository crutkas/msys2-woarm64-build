STATIC_CXX_OBJECTS := $(patsubst ../objects/%,$(STATIC_CXX_DIR)/%,$(NORMAL_OBJS))

$(STATIC_CXX_DIR)/%.o: $(srcdir)/%.cc $(HEADER_DEPS)
	$(LIBTOOL_COMPILE) $(CXX) $(CFLAGS_NORMAL) -c $< -o $@

$(STATIC_CXX_DIR)/libncurses++w.a: $(STATIC_CXX_OBJECTS)
	$(CXX_AR) $(CXX_ARFLAGS) $@ $?
	$(RANLIB) $@

.PHONY: chain-static-cxx
chain-static-cxx: $(STATIC_CXX_DIR)/libncurses++w.a
