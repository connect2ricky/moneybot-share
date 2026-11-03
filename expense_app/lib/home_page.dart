import 'package:flutter/material.dart';

import 'budget_view.dart';
import 'cards_view.dart';
import 'data.dart';
import 'grocery_view.dart';
import 'loans_view.dart';
import 'money.dart';
import 'settings.dart';
import 'settings_page.dart';
import 'spending_view.dart';
import 'sync.dart';
import 'theme.dart';

/// Read-only mobile version of the dashboard. Everything comes from the file the Mac publishes.
class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  static const _titles = ['Spending', 'Budget', 'Grocery', 'Loans', 'Cards'];

  Ledger? _ledger;
  int _tab = 0;
  bool _syncing = false;

  @override
  void initState() {
    super.initState();
    _loadCached();
    _syncQuietly();
  }

  Future<void> _loadCached() async {
    final cached = await AppSettings.cachedLedger();
    if (!mounted || cached == null) return;
    setState(() => _ledger = cached);
  }

  /// On launch the newest data is loaded if possible. Otherwise the last copy stays.
  Future<void> _syncQuietly() async {
    final settings = await AppSettings.syncSettings();
    if (!settings.isSet) return;
    try {
      await _pull(settings);
    } catch (_) {
      // Stay quiet on launch; the sync button shows the reason.
    }
  }

  Future<void> _syncNow() async {
    final settings = await AppSettings.syncSettings();
    if (!mounted) return;
    if (!settings.isSet) return _openSettings();
    setState(() => _syncing = true);
    final messenger = ScaffoldMessenger.of(context);
    try {
      await _pull(settings);
      final when = _ledger?.publishedAt;
      messenger.showSnackBar(SnackBar(content: Text(when == null ? 'Up to date' : 'Up to date as of ${whenLabel(when)}')));
    } on SyncException catch (e) {
      messenger.showSnackBar(SnackBar(content: Text(e.message)));
    } catch (_) {
      messenger.showSnackBar(const SnackBar(content: Text('Could not read the data. Try again shortly.')));
    } finally {
      if (mounted) setState(() => _syncing = false);
    }
  }

  Future<void> _pull(SyncSettings settings) async {
    final body = await SyncClient(settings).fetchSnapshot();
    final ledger = Ledger.parse(body);
    await AppSettings.saveSnapshot(body);
    if (!mounted) return;
    setState(() => _ledger = ledger);
  }

  Future<void> _openSettings() async {
    await Navigator.of(context).push(MaterialPageRoute(builder: (_) => const SettingsPage()));
    if (mounted) _syncQuietly();
  }

  @override
  Widget build(BuildContext context) {
    final ledger = _ledger;
    final when = ledger?.publishedAt;
    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(_titles[_tab], style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700, letterSpacing: -0.3)),
            if (when != null)
              Text('As of ${whenLabel(when)}',
                  style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.onSurfaceVariant)),
          ],
        ),
        actions: [
          IconButton(
            tooltip: 'Sync',
            onPressed: _syncing ? null : _syncNow,
            icon: _syncing
                ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.sync),
          ),
          IconButton(tooltip: 'Settings', onPressed: _openSettings, icon: const Icon(Icons.settings_outlined)),
          const SizedBox(width: 4),
        ],
      ),
      body: ledger == null
          ? _NotSynced(onSetUp: _syncNow)
          : RefreshIndicator(
              onRefresh: _syncNow,
              child: IndexedStack(
                index: _tab,
                children: [
                  SpendingView(ledger: ledger),
                  BudgetView(ledger: ledger),
                  GroceryView(ledger: ledger),
                  LoansView(ledger: ledger),
                  CardsView(ledger: ledger),
                ],
              ),
            ),
      bottomNavigationBar: DecoratedBox(
        decoration: BoxDecoration(border: Border(top: BorderSide(color: context.palette.line))),
        child: NavigationBar(
          selectedIndex: _tab,
          onDestinationSelected: (i) => setState(() => _tab = i),
          destinations: const [
            NavigationDestination(icon: Icon(Icons.receipt_long_outlined), selectedIcon: Icon(Icons.receipt_long), label: 'Spending'),
            NavigationDestination(icon: Icon(Icons.savings_outlined), selectedIcon: Icon(Icons.savings), label: 'Budget'),
            NavigationDestination(icon: Icon(Icons.shopping_basket_outlined), selectedIcon: Icon(Icons.shopping_basket), label: 'Grocery'),
            NavigationDestination(icon: Icon(Icons.account_balance_outlined), selectedIcon: Icon(Icons.account_balance), label: 'Loans'),
            NavigationDestination(icon: Icon(Icons.credit_card_outlined), selectedIcon: Icon(Icons.credit_card), label: 'Cards'),
          ],
        ),
      ),
    );
  }
}

class _NotSynced extends StatelessWidget {
  const _NotSynced({required this.onSetUp});
  final VoidCallback onSetUp;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.cloud_download_outlined, size: 40, color: context.palette.faint),
            const SizedBox(height: 12),
            const Text('No data yet', style: TextStyle(fontSize: 17, fontWeight: FontWeight.w600)),
            const SizedBox(height: 4),
            Text(
              'Load your data from the copy your Mac keeps on GitHub.',
              textAlign: TextAlign.center,
              style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant),
            ),
            const SizedBox(height: 16),
            FilledButton(onPressed: onSetUp, child: const Text('Sync now')),
          ],
        ),
      ),
    );
  }
}
