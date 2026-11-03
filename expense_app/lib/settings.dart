import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'data.dart';
import 'sync.dart';

class AppSettings {
  static const _token = 'github_token';
  static const _key = 'phone_key';
  static const _lastSync = 'last_sync';
  static const _snapshot = 'snapshot_json';
  static const _balancesHidden = 'balances_hidden';
  static const _shutPanels = 'shut_panels';
  static const _secure = FlutterSecureStorage();

  /// Pre-filled values for a personal build: `--dart-define=GITHUB_TOKEN=... --dart-define=PHONE_KEY=...`.
  /// Used only until something is saved in Settings; store builds leave both empty.
  static const _defaultToken = String.fromEnvironment('GITHUB_TOKEN');
  static const _defaultKey = String.fromEnvironment('PHONE_KEY');

  static Future<Set<String>> shutPanels() async =>
      ((await SharedPreferences.getInstance()).getStringList(_shutPanels) ?? const []).toSet();

  static Future<void> saveShutPanels(Set<String> titles) async =>
      (await SharedPreferences.getInstance()).setStringList(_shutPanels, titles.toList());

  static Future<SyncSettings> syncSettings() async => SyncSettings(
        token: await _secure.read(key: _token) ?? _defaultToken,
        key: await _secure.read(key: _key) ?? _defaultKey,
      );

  static Future<void> saveSyncSettings(SyncSettings s) async {
    await _secure.write(key: _token, value: s.token.trim());
    await _secure.write(key: _key, value: s.key.trim());
  }

  static Future<DateTime?> lastSync() async {
    final prefs = await SharedPreferences.getInstance();
    final millis = prefs.getInt(_lastSync);
    return millis == null ? null : DateTime.fromMillisecondsSinceEpoch(millis);
  }

  /// The last data received, so the app works offline with the last copy.
  static Future<Ledger?> cachedLedger() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_snapshot);
    if (raw == null) return null;
    try {
      return Ledger.parse(raw);
    } catch (_) {
      return null;
    }
  }

  static Future<void> saveSnapshot(String json) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_snapshot, json);
    await prefs.setInt(_lastSync, DateTime.now().millisecondsSinceEpoch);
  }

  static Future<bool> balancesHidden() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_balancesHidden) ?? false;
  }

  static Future<void> setBalancesHidden(bool hidden) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_balancesHidden, hidden);
  }
}
