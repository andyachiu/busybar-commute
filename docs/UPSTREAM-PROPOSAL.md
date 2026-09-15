# Upstream Proposal: Fix Si917 Wi-Fi Coprocessor State Deadlock After Firmware Update

## Summary

When updating firmware via `/api/update` (or `./fbt flash_usb`), the device can enter a state where `/api/wifi/networks` rejects scans with `400 {"error":"Scan not possible when connected"}` or `503 {"error":"Generic error"}`, leaving the companion app Wi-Fi network list permanently empty.

This is caused by two bugs:
1. `updater.c` reboots with `PowerRebootNormalU5` upon applying an update, which resets only the STM32 main MCU while leaving the battery-powered Si917 wireless coprocessor running in its prior association state.
2. `api_wifi_disconnect_and_forget()` aborts if `wifi_disconnect()` returns anything other than `WifiStatusOk`. If the MCU boots up with its internal state marked `disconnected`, it treats disconnect requests as `WifiStatusAlreadyDisconnected` and skips `wifi_forget()`, preventing the user from clearing the coprocessor state.

---

## Root Cause Analysis

### 1. `updater_do_installation_apply` uses `PowerRebootNormalU5`

In `applications/system/updater/updater.c:241`:
```c
power_reboot(instance->power, PowerRebootNormalU5);
```

In `power_handle_reboot` (`applications/services/power/power_service/power.c`), `furi_hal_power_reset_917(false)` is only invoked for `PowerRebootNormal` and `PowerRebootNormal917`. For `PowerRebootNormalU5`, only `furi_hal_cortex_system_reset()` is called. 

Because the BusyBar has an internal battery, the Si917 coprocessor never loses power across the update. When the newly flashed STM32 MCU boots, its software state starts fresh as `WifiStateDisconnected`, but the coprocessor remains associated or in an uncoordinated state. When a scan is subsequently requested:
- The Si917 driver returns `SL_STATUS_SI91X_SCAN_ISSUED_IN_ASSOCIATED_STATE`.
- `wifi_decode_sl_status()` maps this to `WifiStatusScanNotPossible`.
- `api_wifi.c` returns HTTP 400 `Scan not possible when connected`.

### 2. Disconnect/forget deadlock in `api_wifi_disconnect_and_forget`

In `applications/services/web_server/http_api/api_wifi.c:132-140`:
```c
static WifiStatus api_wifi_disconnect_and_forget(void) {
    WifiStatus status;
    Wifi* wifi = furi_record_open(RECORD_WIFI);
    do {
        status = wifi_disconnect(wifi);
        if(status != WifiStatusOk) {
            break;
        }
        status = wifi_forget(wifi);
    } while(false);
    furi_record_close(RECORD_WIFI);
    return status;
}
```

When the MCU software state is `WifiStateDisconnected`, calling `wifi_disconnect()` returns `WifiStatusAlreadyDisconnected`. Because of the `if(status != WifiStatusOk) break;` check, execution exits immediately without calling `wifi_forget(wifi)` to reset settings or clear network credentials.

---

## Proposed Patches

### Patch 1: Reset Si917 during updater reboot

Drive `gpio_917_rst` low during updater restart to ensure the coprocessor and main MCU initialize together in sync:

```diff
diff --git a/applications/system/updater/updater.c b/applications/system/updater/updater.c
index 9657db4..e93c11e 100644
--- a/applications/system/updater/updater.c
+++ b/applications/system/updater/updater.c
@@ -238,7 +238,7 @@ static UpdaterStatus updater_do_installation_apply(Updater* instance, UpdaterMes
     FURI_LOG_D(TAG, "Boot mode set to \"update\", device will reboot...");
 
     furi_delay_ms(UPDATE_INSTALLATION_APPLY_REBOOT_DELAY);
-    power_reboot(instance->power, PowerRebootNormalU5);
+    power_reboot(instance->power, PowerRebootNormal);
 
     furi_crash();
 }
```

### Patch 2: Allow network forget when already disconnected

Ensure `wifi_forget()` executes even when the MCU state already reports disconnected:

```diff
diff --git a/applications/services/web_server/http_api/api_wifi.c b/applications/services/web_server/http_api/api_wifi.c
index 232ce06..0b253b7 100644
--- a/applications/services/web_server/http_api/api_wifi.c
+++ b/applications/services/web_server/http_api/api_wifi.c
@@ -132,7 +132,7 @@ static WifiStatus api_wifi_disconnect_and_forget(void) {
 
     do {
         status = wifi_disconnect(wifi);
-        if(status != WifiStatusOk) {
+        if(status != WifiStatusOk && status != WifiStatusAlreadyDisconnected) {
             break;
         }
         status = wifi_forget(wifi);
```

---

## Verification

1. Flashed firmware with Patch 1 and Patch 2.
2. Verified `updater_do_installation_apply` cleanly power-resets the Si917 coprocessor via `gpio_917_rst`.
3. Verified `POST /api/wifi/disconnect` succeeds and allows `GET /api/wifi/networks` to scan and return visible APs immediately.
