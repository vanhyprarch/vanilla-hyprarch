#define _POSIX_C_SOURCE 200809L

/*
 * ColorMix algorithm translated from Ly's src/animations/ColorMix.zig at
 * commit 863162b5f79850c08fda13a3fbde7e19aac544ba. Ly is distributed under
 * the Do What The Fuck You Want To Public License, Version 2 (WTFPL).
 * This standalone experimental translation does not claim original authorship
 * of Ly's algorithm and does not copy unrelated display-manager code.
 */

#include <errno.h>
#include <math.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>

#define ARRAY_LEN(array) (sizeof(array) / sizeof((array)[0]))

enum {
    LY_REFERENCE_DELAY_MS = 5,
    DEFAULT_DELAY_MS = 33,
    SGR_CAPACITY = 64,
};

static const float TIME_SCALE = 0.01f;
static const float TWO_PI = 6.28318530717958647692f;

static const char ENTER_TERMINAL[] =
    "\x1b[?1049h\x1b[?25l\x1b[0m\x1b[2J\x1b[H";
static const char RESTORE_TERMINAL[] =
    "\x1b[0m\x1b[?25h\x1b[?1049l";
static const char CLEAR_AND_HOME[] = "\x1b[2J\x1b[H";
static const char HOME[] = "\x1b[H";

typedef struct {
    unsigned int red;
    unsigned int green;
    unsigned int blue;
} Rgb;

typedef struct {
    const char *glyph;
    unsigned int color_pair;
} PaletteCell;

typedef struct {
    char *data;
    size_t capacity;
} FrameBuffer;

/* U+2588, U+2593, U+2592, U+2591 in UTF-8, in Ly's palette order. */
static const PaletteCell PALETTE[] = {
    {"\xe2\x96\x88", 0},
    {"\xe2\x96\x93", 0},
    {"\xe2\x96\x92", 0},
    {"\xe2\x96\x91", 0},
    {"\xe2\x96\x88", 1},
    {"\xe2\x96\x93", 1},
    {"\xe2\x96\x92", 1},
    {"\xe2\x96\x91", 1},
    {"\xe2\x96\x88", 2},
    {"\xe2\x96\x93", 2},
    {"\xe2\x96\x92", 2},
    {"\xe2\x96\x91", 2},
};

static volatile sig_atomic_t stop_requested = 0;
static volatile sig_atomic_t resize_requested = 1;
static bool terminal_active = false;

static void request_stop(int signal_number)
{
    (void)signal_number;
    stop_requested = 1;
}

static void request_resize(int signal_number)
{
    (void)signal_number;
    resize_requested = 1;
}

static int write_all(const char *data, size_t length, bool honor_stop)
{
    size_t written = 0;

    while (written < length) {
        ssize_t result = write(STDOUT_FILENO, data + written, length - written);

        if (result > 0) {
            written += (size_t)result;
            continue;
        }
        if (result < 0 && errno == EINTR) {
            if (honor_stop && stop_requested) {
                return -1;
            }
            continue;
        }
        return -1;
    }

    return 0;
}

static void restore_terminal(void)
{
    if (!terminal_active) {
        return;
    }

    terminal_active = false;
    (void)write_all(RESTORE_TERMINAL, sizeof(RESTORE_TERMINAL) - 1, false);
}

static int install_signal_handlers(void)
{
    struct sigaction stop_action;
    struct sigaction resize_action;

    memset(&stop_action, 0, sizeof(stop_action));
    stop_action.sa_handler = request_stop;
    sigemptyset(&stop_action.sa_mask);

    memset(&resize_action, 0, sizeof(resize_action));
    resize_action.sa_handler = request_resize;
    sigemptyset(&resize_action.sa_mask);

    if (sigaction(SIGINT, &stop_action, NULL) < 0 ||
        sigaction(SIGTERM, &stop_action, NULL) < 0 ||
        sigaction(SIGHUP, &stop_action, NULL) < 0 ||
        sigaction(SIGWINCH, &resize_action, NULL) < 0) {
        return -1;
    }

    return 0;
}

static int get_terminal_size(unsigned int *columns, unsigned int *rows)
{
    struct winsize size;

    if (ioctl(STDOUT_FILENO, TIOCGWINSZ, &size) < 0 ||
        size.ws_col == 0 || size.ws_row == 0) {
        return -1;
    }

    *columns = size.ws_col;
    *rows = size.ws_row;
    return 0;
}

static int ensure_frame_capacity(
    FrameBuffer *buffer,
    unsigned int columns,
    unsigned int rows)
{
    const size_t bytes_per_cell = SGR_CAPACITY + 3;
    size_t cell_count;
    size_t required;
    char *new_data;

    if ((size_t)rows > SIZE_MAX / (size_t)columns) {
        errno = EOVERFLOW;
        return -1;
    }
    cell_count = (size_t)columns * (size_t)rows;

    if (cell_count > (SIZE_MAX - 64 - (size_t)rows * 2) / bytes_per_cell) {
        errno = EOVERFLOW;
        return -1;
    }
    required = cell_count * bytes_per_cell + (size_t)rows * 2 + 64;

    if (required <= buffer->capacity) {
        return 0;
    }

    new_data = realloc(buffer->data, required);
    if (new_data == NULL) {
        return -1;
    }

    buffer->data = new_data;
    buffer->capacity = required;
    return 0;
}

static int append_bytes(
    FrameBuffer *buffer,
    size_t *length,
    const char *data,
    size_t data_length)
{
    if (*length > buffer->capacity ||
        data_length > buffer->capacity - *length) {
        errno = EOVERFLOW;
        return -1;
    }

    memcpy(buffer->data + *length, data, data_length);
    *length += data_length;
    return 0;
}

static float vector_length(float x, float y)
{
    return sqrtf(x * x + y * y);
}

static float random_pattern_offset(void)
{
    float unit = (float)((double)rand() / ((double)RAND_MAX + 1.0));
    float offset = unit * TWO_PI;

    if (offset >= TWO_PI) {
        offset = nextafterf(TWO_PI, 0.0f);
    }

    return offset;
}

static unsigned int random_seed(void)
{
    struct timespec now;
    uint64_t seed = (uint64_t)(unsigned long)getpid();

    if (clock_gettime(CLOCK_REALTIME, &now) == 0) {
        seed ^= (uint64_t)now.tv_sec;
        seed ^= (uint64_t)now.tv_nsec << 21;
    }

    seed ^= seed >> 32;
    return (unsigned int)seed;
}

static int format_sgr(
    char destination[SGR_CAPACITY],
    const Rgb foreground,
    const Rgb background)
{
    int length = snprintf(
        destination,
        SGR_CAPACITY,
        "\x1b[0;38;2;%u;%u;%u;48;2;%u;%u;%um",
        foreground.red,
        foreground.green,
        foreground.blue,
        background.red,
        background.green,
        background.blue);

    if (length < 0 || length >= SGR_CAPACITY) {
        errno = EOVERFLOW;
        return -1;
    }

    return length;
}

static int render_frame(
    FrameBuffer *buffer,
    unsigned int columns,
    unsigned int rows,
    double *animation_frames,
    double animation_step,
    float pattern_cos_mod,
    float pattern_sin_mod,
    char sgr[3][SGR_CAPACITY],
    const size_t sgr_lengths[3],
    bool clear_screen)
{
    size_t output_length = 0;
    int active_pair = -1;
    float time;

    /* Keep Ly's 5 ms motion while allowing a slower render cadence. */
    *animation_frames += animation_step;
    /* Cast before applying the f32 scale, preserving the 5 ms code path. */
    time = (float)(*animation_frames) * TIME_SCALE;

    if (clear_screen) {
        if (append_bytes(
                buffer,
                &output_length,
                CLEAR_AND_HOME,
                sizeof(CLEAR_AND_HOME) - 1) < 0) {
            return -1;
        }
    } else if (append_bytes(
                   buffer,
                   &output_length,
                   HOME,
                   sizeof(HOME) - 1) < 0) {
        return -1;
    }

    for (unsigned int y = 0; y < rows; ++y) {
        if (stop_requested) {
            return 1;
        }

        for (unsigned int x = 0; x < columns; ++x) {
            float uv_x = (float)((int)x * 2 - (int)columns) /
                (float)(rows * 2U);
            float uv_y = (float)((int)y * 2 - (int)rows) / (float)rows;
            float uv2_x = uv_x + uv_y;
            float uv2_y = uv_x + uv_y;

            for (unsigned int iteration = 0; iteration < 3; ++iteration) {
                float length = vector_length(uv_x, uv_y);
                float shared;

                uv2_x += uv_x + length;
                uv2_y += uv_y + length;
                uv_x += 0.5f * cosf(
                    pattern_cos_mod + uv2_y * 0.2f + time * 0.1f);
                uv_y += 0.5f * sinf(
                    pattern_sin_mod + uv2_x - time * 0.1f);
                shared = 1.0f * cosf(uv_x + uv_y) -
                    sinf(uv_x * 0.7f - uv_y);
                uv_x -= shared;
                uv_y -= shared;
            }

            size_t palette_index =
                (size_t)floorf(vector_length(uv_x, uv_y) * 5.0f) %
                ARRAY_LEN(PALETTE);
            const PaletteCell *cell = &PALETTE[palette_index];

            if ((int)cell->color_pair != active_pair) {
                if (append_bytes(
                        buffer,
                        &output_length,
                        sgr[cell->color_pair],
                        sgr_lengths[cell->color_pair]) < 0) {
                    return -1;
                }
                active_pair = (int)cell->color_pair;
            }

            if (append_bytes(buffer, &output_length, cell->glyph, 3) < 0) {
                return -1;
            }
        }

        if (y + 1 < rows &&
            append_bytes(buffer, &output_length, "\r\n", 2) < 0) {
            return -1;
        }
    }

    return write_all(buffer->data, output_length, true);
}

static int sleep_milliseconds(unsigned int milliseconds)
{
    struct timespec remaining = {
        .tv_sec = (time_t)(milliseconds / 1000U),
        .tv_nsec = (long)(milliseconds % 1000U) * 1000000L,
    };

    while (nanosleep(&remaining, &remaining) < 0) {
        if (errno != EINTR) {
            return -1;
        }
        if (stop_requested || resize_requested) {
            return 0;
        }
    }

    return 0;
}

static int parse_delay(const char *value, unsigned int *delay_ms)
{
    char *end = NULL;
    unsigned long parsed;

    errno = 0;
    parsed = strtoul(value, &end, 10);
    if (errno != 0 || end == value || *end != '\0' ||
        parsed == 0 || parsed > UINT16_MAX) {
        return -1;
    }

    *delay_ms = (unsigned int)parsed;
    return 0;
}

static void print_help(FILE *stream, const char *program)
{
    fprintf(
        stream,
        "Usage: %s [--delay-ms MILLISECONDS]\n"
        "\n"
        "Render Ly's colormix animation in the current terminal.\n"
        "\n"
        "Options:\n"
        "  --delay-ms N  delay after each frame (1-65535, default: 33)\n"
        "  --print-animation-step\n"
        "                print Ly-equivalent frames per render and exit\n"
        "  -h, --help    show this help and exit\n"
        "\n"
        "Press Ctrl+C to exit.\n",
        program);
}

int main(int argc, char **argv)
{
    const Rgb red = {255, 0, 0};
    const Rgb blue = {0, 0, 255};
    /* Ly/termbox2 TB_HI_BLACK means explicit RGB black, not default color. */
    const Rgb true_black = {0, 0, 0};
    const Rgb foregrounds[3] = {red, blue, true_black};
    const Rgb backgrounds[3] = {blue, true_black, red};
    char sgr[3][SGR_CAPACITY];
    size_t sgr_lengths[3];
    FrameBuffer frame_buffer = {0};
    unsigned int delay_ms = DEFAULT_DELAY_MS;
    unsigned int columns = 0;
    unsigned int rows = 0;
    double animation_frames = 0.0;
    double animation_step;
    float pattern_cos_mod;
    float pattern_sin_mod;
    bool print_animation_step = false;
    int exit_status = EXIT_SUCCESS;

    for (int index = 1; index < argc; ++index) {
        if (strcmp(argv[index], "-h") == 0 ||
            strcmp(argv[index], "--help") == 0) {
            print_help(stdout, argv[0]);
            return EXIT_SUCCESS;
        }
        if (strcmp(argv[index], "--delay-ms") == 0) {
            if (++index >= argc || parse_delay(argv[index], &delay_ms) < 0) {
                fprintf(stderr, "invalid --delay-ms value\n");
                return EXIT_FAILURE;
            }
            continue;
        }
        if (strcmp(argv[index], "--print-animation-step") == 0) {
            print_animation_step = true;
            continue;
        }

        fprintf(stderr, "unknown option: %s\n", argv[index]);
        print_help(stderr, argv[0]);
        return EXIT_FAILURE;
    }

    animation_step =
        (double)delay_ms / (double)LY_REFERENCE_DELAY_MS;
    if (print_animation_step) {
        printf("animation-frame-step=%.15g\n", animation_step);
        return EXIT_SUCCESS;
    }

    if (!isatty(STDOUT_FILENO)) {
        fprintf(stderr, "colormix: standard output is not a terminal\n");
        return EXIT_FAILURE;
    }
    if (install_signal_handlers() < 0) {
        perror("colormix: sigaction");
        return EXIT_FAILURE;
    }
    if (atexit(restore_terminal) != 0) {
        fprintf(stderr, "colormix: could not register terminal cleanup\n");
        return EXIT_FAILURE;
    }

    for (size_t index = 0; index < ARRAY_LEN(sgr); ++index) {
        int length = format_sgr(
            sgr[index], foregrounds[index], backgrounds[index]);
        if (length < 0) {
            perror("colormix: format color sequence");
            return EXIT_FAILURE;
        }
        sgr_lengths[index] = (size_t)length;
    }

    srand(random_seed());
    pattern_cos_mod = random_pattern_offset();
    pattern_sin_mod = random_pattern_offset();

    terminal_active = true;
    if (write_all(ENTER_TERMINAL, sizeof(ENTER_TERMINAL) - 1, false) < 0) {
        perror("colormix: enter alternate screen");
        return EXIT_FAILURE;
    }

    while (!stop_requested) {
        bool clear_screen = false;

        if (resize_requested) {
            unsigned int new_columns;
            unsigned int new_rows;

            resize_requested = 0;
            if (get_terminal_size(&new_columns, &new_rows) < 0) {
                perror("colormix: query terminal size");
                exit_status = EXIT_FAILURE;
                break;
            }
            if (ensure_frame_capacity(
                    &frame_buffer, new_columns, new_rows) < 0) {
                perror("colormix: allocate frame buffer");
                exit_status = EXIT_FAILURE;
                break;
            }

            columns = new_columns;
            rows = new_rows;
            clear_screen = true;
        }

        int render_result = render_frame(
            &frame_buffer,
            columns,
            rows,
            &animation_frames,
            animation_step,
            pattern_cos_mod,
            pattern_sin_mod,
            sgr,
            sgr_lengths,
            clear_screen);
        if (render_result < 0 && !stop_requested) {
            perror("colormix: render frame");
            exit_status = EXIT_FAILURE;
            break;
        }
        if (render_result != 0 || stop_requested) {
            break;
        }
        if (sleep_milliseconds(delay_ms) < 0) {
            perror("colormix: frame delay");
            exit_status = EXIT_FAILURE;
            break;
        }
    }

    free(frame_buffer.data);
    restore_terminal();
    return exit_status;
}
