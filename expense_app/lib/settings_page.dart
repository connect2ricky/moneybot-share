import 'package:flutter/material.dart';

import 'data.dart';
import 'money.dart';
import 'settings.dart';
import 'sync.dart';
import 'widgets.dart';

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  final _token = TextEditingController();
  final _key = TextEditingController();
  String? _message;
  bool _busy = false;
  DateTime? _lastSync;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final s = await AppSettings.syncSettings();
    final last = await AppSettings.lastSync();
    if (!mounted) return;
    _token.text = s.token;
    _key.text = s.key;
    setState(() => _lastSync = last);
  }

  @override
  void dispose() {
    _token.dispose();
    _key.dispose();
    super.dispose();
  }

  SyncSettings get _current => SyncSettings(token: _token.text.trim(), key: _key.text.trim());

  /// Saved only once it works, so a mistyped key cannot replace a good one.
  Future<void> _testAndSave() async {
    setState(() {
      _busy = true;
      _message = 'Checking…';
    });
    try {
      final body = await SyncClient(_current).fetchSnapshot();
      Ledger.parse(body);
      await AppSettings.saveSyncSettings(_current);
      await AppSettings.saveSnapshot(body);
      if (mounted) setState(() => _message = 'Connected and saved.');
    } on SyncException catch (e) {
      if (mounted) setState(() => _message = e.message);
    } catch (_) {
      if (mounted) setState(() => _message = 'The data could not be read.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        padding: pagePadding,
        children: [
          Panel(
            title: 'Sync',
            note: 'Your Mac keeps an encrypted copy of the dashboard in your private GitHub repository. '
                'This app downloads it. Nothing is sent from the phone.',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                TextField(
                  controller: _token,
                  obscureText: true,
                  autocorrect: false,
                  decoration: const InputDecoration(
                    labelText: 'GitHub token',
                    helperText: 'Read-only, for the moneybot-data repository',
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _key,
                  obscureText: true,
                  autocorrect: false,
                  decoration: const InputDecoration(
                    labelText: 'Phone key',
                    helperText: 'On the Mac: moneybot phone-key',
                  ),
                ),
                const SizedBox(height: 14),
                FilledButton(onPressed: _busy ? null : _testAndSave, child: const Text('Test and save')),
                if (_message != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 10),
                    child: Text(_message!, style: TextStyle(color: muted)),
                  ),
              ],
            ),
          ),
          Text(
            _lastSync == null ? 'Not synced yet.' : 'Last synced ${whenLabel(_lastSync!)}',
            style: TextStyle(fontSize: 13, color: muted),
          ),
        ],
      ),
    );
  }
}
