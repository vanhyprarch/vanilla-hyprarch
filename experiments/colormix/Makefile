CC ?= cc
CPPFLAGS ?=
CFLAGS ?= -O2
CFLAGS += -std=c11 -Wall -Wextra -Wpedantic
LDFLAGS ?=
LDLIBS += -lm

TARGET := colormix

.PHONY: all clean

all: $(TARGET)

$(TARGET): colormix.c
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) -o $@ $< $(LDLIBS)

clean:
	$(RM) $(TARGET)
