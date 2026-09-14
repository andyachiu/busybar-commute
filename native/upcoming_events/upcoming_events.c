#include "snapshot.h"
#include <apps_menu/apps_menu.h>
#include <furi.h>
#include <gui/gui.h>
#include <gui/modules/anim_player.h>
#include <gui/modules/label.h>
#include <stdio.h>
#include <storage/storage.h>
#include <string.h>
#include <time/time.h>

#define SNAPSHOT_A EXT_PATH("user_assets/commute-bar/events-a.bin")
#define SNAPSHOT_B EXT_PATH("user_assets/commute-bar/events-b.bin")
#define FRONT_SCROLL_SPEED 20

typedef struct {
  Gui *gui;
  FuriMessageQueue *inputs;
  EventSnapshot snapshot;
  unsigned selected;
  bool details;
  Label *front;
  Label *back;
  AnimPlayer *icon;
  char icon_kind[16];
} Browser;

static void set_icon(Browser *app, const char *kind) {
  if (strcmp(app->icon_kind, kind) == 0)
    return;
  const char *file = "event-background.anim";
  if (strcmp(kind, "baseball") == 0)
    file = "baseball-background.anim";
  else if (strcmp(kind, "basketball") == 0)
    file = "basketball-background.anim";
  else if (strcmp(kind, "convention") == 0)
    file = "convention-background.anim";
  else if (strcmp(kind, "detour") == 0)
    file = "detour-background.anim";
  char path[96];
  snprintf(path, sizeof(path), EXT_PATH("user_assets/commute-bar/%s"), file);
  anim_player_set_source(app->icon, path);
  strncpy(app->icon_kind, kind, sizeof(app->icon_kind) - 1);
}

static void load_snapshot(Browser *app) {
  Storage *storage = furi_record_open(RECORD_STORAGE);
  File *file = storage_file_alloc(storage);
  uint8_t *bytes = malloc(SNAPSHOT_MAX);
  EventSnapshot *candidate = malloc(sizeof(EventSnapshot));
  const char *paths[] = {SNAPSHOT_A, SNAPSHOT_B};
  for (unsigned slot = 0; slot < 2; ++slot) {
    if (storage_file_open(file, paths[slot], FSAM_READ, FSOM_OPEN_EXISTING)) {
      uint64_t size = storage_file_size(file);
      if (size <= SNAPSHOT_MAX &&
          storage_file_read(file, bytes, size) == size &&
          snapshot_decode(bytes, size, candidate) &&
          candidate->fetched >= app->snapshot.fetched)
        memcpy(&app->snapshot, candidate, sizeof(EventSnapshot));
      storage_file_close(file);
    }
  }
  storage_file_free(file);
  furi_record_close(RECORD_STORAGE);
  free(bytes);
  free(candidate);
  if (app->snapshot.count)
    app->selected %= app->snapshot.count;
}

static void set_front_event(Browser *app, const EventRow *row) {
  size_t title_width = strlen(row->title);
  size_t timing_width = strlen(row->timing);
  int width = (int)(title_width > timing_width ? title_width : timing_width);
  label_set_text_fmt(app->front, "%-*s\n%-*s", width, row->title, width,
                     row->timing);
}

static void render(Browser *app) {
  with_gui(app->gui, {
    if (!app->snapshot.count) {
      label_set_text(app->front, "EVENTS\nNO CACHE");
      label_set_text(app->back,
                     "Upcoming Events\nNo cached events\nBack: Apps menu");
    } else {
      EventRow *row = &app->snapshot.rows[app->selected];
      time_t now = time_get_timestamp();
      bool stale =
          now < app->snapshot.fetched || now - app->snapshot.fetched > 3600;
      set_front_event(app, row);
      set_icon(app, row->kind);
      if (app->details) {
        label_set_text_fmt(
            app->back, "%s\n%s\n%s\n%s\n%s / age %lu min", row->title,
            row->venue, row->timing, row->departure, stale ? "STALE" : "Cached",
            (unsigned long)(now >= app->snapshot.fetched
                                ? (now - app->snapshot.fetched) / 60
                                : 0));
      } else {
        label_set_text_fmt(app->back,
                           "EVENT %u/%lu - %s\n%s\n%s\nTurn: browse / OK: "
                           "details\nBack: Apps menu",
                           app->selected + 1,
                           (unsigned long)app->snapshot.count,
                           stale ? "STALE" : "CACHED", row->title, row->timing);
      }
    }
  });
}

static bool input_callback(const InputEvent *event, void *context) {
  Browser *app = context;
  if (event->type != InputTypeShort)
    return false;
  if (event->key != InputKeyUp && event->key != InputKeyDown &&
      event->key != InputKeyOk && event->key != InputKeyBack)
    return false;
  /* Never block the GUI thread when a fast wheel fills the queue. */
  furi_message_queue_put(app->inputs, event, 0);
  return true;
}

int32_t upcoming_events_entry(void *argument) {
  UNUSED(argument);
  Browser *app = malloc(sizeof(Browser));
  memset(app, 0, sizeof(Browser));
  app->inputs = furi_message_queue_alloc(16, sizeof(InputEvent));
  app->gui = furi_record_open(RECORD_GUI);
  load_snapshot(app);
  with_gui(app->gui, {
    GuiLayer *layer = gui_get_layer(app->gui, GuiLayerIdMain);
    app->icon =
        anim_player_alloc(gui_layer_get_root_widget(layer, GuiDisplayIdFront));
    widget_set_size(anim_player_get_base(app->icon), 72, 16);
    app->front =
        label_alloc(gui_layer_get_root_widget(layer, GuiDisplayIdFront));
    widget_set_pos(label_get_base(app->front), 18, 0);
    widget_set_size(label_get_base(app->front), 54, 16);
    label_set_text_font_size(app->front, LabelFontSizeSmall);
    label_set_line_spacing(app->front, -2);
    label_set_long_content_mode(app->front, LabelLongContentModeScrollCircular);
    label_set_long_content_anim_speed(app->front, FRONT_SCROLL_SPEED);
    app->back = label_alloc(gui_layer_get_root_widget(layer, GuiDisplayIdBack));
    widget_set_size(label_get_base(app->back), 160, 80);
    label_set_text_font_size(app->back, LabelFontSizeSmall);
    label_set_long_content_mode(app->back, LabelLongContentModeWrap);
    gui_layer_add_input_callback(layer, input_callback, app);
  });
  render(app);
  for (;;) {
    InputEvent event;
    if (furi_message_queue_get(app->inputs, &event, furi_ms_to_ticks(60000)) !=
        FuriStatusOk) {
      load_snapshot(app);
      render(app);
      continue;
    }
    if (event.key == InputKeyBack) {
      if (app->details)
        app->details = false;
      else {
        if (apps_menu_start(AppsMenuModeShowMenu))
          break;
      }
    } else if (app->snapshot.count) {
      if (event.key == InputKeyOk)
        app->details = !app->details;
      if (event.key == InputKeyUp)
        app->selected = (app->selected + 1) % app->snapshot.count;
      if (event.key == InputKeyDown)
        app->selected =
            (app->selected + app->snapshot.count - 1) % app->snapshot.count;
    }
    render(app);
  }
  with_gui(app->gui, {
    gui_layer_remove_input_callback(gui_get_layer(app->gui, GuiLayerIdMain),
                                    input_callback);
    label_free(app->front);
    anim_player_free(app->icon);
    label_free(app->back);
  });
  furi_record_close(RECORD_GUI);
  furi_message_queue_free(app->inputs);
  free(app);
  return 0;
}
