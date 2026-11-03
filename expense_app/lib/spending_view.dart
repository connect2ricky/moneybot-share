import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'data.dart';
import 'money.dart';
import 'settings.dart';
import 'theme.dart';
import 'widgets.dart';

/// The dashboard's spending page, read-only. Changes are made on the Mac.
class SpendingView extends StatefulWidget {
  const SpendingView({super.key, required this.ledger});
  final Ledger ledger;

  @override
  State<SpendingView> createState() => _SpendingViewState();
}

class _SpendingViewState extends State<SpendingView> {
  String? _month;
  String _account = '';
  String _compare = 'prev';
  bool _noLoans = false;
  String _query = '';
  bool _balancesHidden = false;

  @override
  void initState() {
    super.initState();
    AppSettings.balancesHidden().then((hidden) {
      if (mounted) setState(() => _balancesHidden = hidden);
    });
  }

  void _setBalancesHidden(bool hidden) {
    setState(() => _balancesHidden = hidden);
    AppSettings.setBalancesHidden(hidden);
  }

  @override
  Widget build(BuildContext context) {
    final led = widget.ledger;
    final months = monthsWithGaps(led.transactions);
    final month = _month != null && months.contains(_month)
        ? _month!
        : (months.isEmpty ? monthKey(DateTime.now()) : months.last);
    final accounts = led.transactions.map((t) => t.account).toSet().toList()..sort();
    final account = accounts.contains(_account) ? _account : '';
    final cm = _compare == 'prev'
        ? shiftMonth(month, -1)
        : _compare == 'year'
        ? shiftMonth(month, -12)
        : null;
    final now = totalsFor(led, month, account);
    final was = cm == null ? null : totalsFor(led, cm, account);
    final has = was != null && was.count > 0;
    final waiting = led.transactions.where((t) => t.pending).toList();

    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: pagePadding,
      children: [
        _filters(months, month, accounts, account, cm),
        _summary(now, was, has, cm, waiting.length, soFar(led, month, account, now.spend, DateTime.now()),
            leftLine(led, month, account, now.spend)),
        if (led.balances.isNotEmpty) _balances(led),
        if (waiting.isNotEmpty) _review(waiting),
        _categories(led, now, has ? was : null, month, account),
        if (months.length > 1) _trend(led, month, account, months),
        _days(led, month, account),
        _transactions(led, month, account),
      ],
    );
  }

  Widget _filters(List<String> months, String month, List<String> accounts, String account, String? cm) {
    final i = months.indexOf(month);
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          IconButton(
            tooltip: 'Previous month',
            visualDensity: VisualDensity.compact,
            onPressed: i > 0 ? () => setState(() => _month = months[i - 1]) : null,
            icon: const Icon(Icons.chevron_left),
          ),
          PopupMenuButton<String>(
            tooltip: 'Choose month',
            initialValue: month,
            onSelected: (m) => setState(() => _month = m),
            itemBuilder: (_) => [for (final m in months.reversed) PopupMenuItem(value: m, child: Text(monthName(m)))],
            child: Text(monthName(month), style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
          ),
          IconButton(
            tooltip: 'Next month',
            visualDensity: VisualDensity.compact,
            onPressed: i >= 0 && i < months.length - 1 ? () => setState(() => _month = months[i + 1]) : null,
            icon: const Icon(Icons.chevron_right),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Align(
              alignment: Alignment.centerRight,
              child: PopupMenuButton<String>(
                tooltip: 'Choose account',
                initialValue: account,
                onSelected: (a) => setState(() => _account = a),
                itemBuilder: (_) => [
                  const PopupMenuItem(value: '', child: Text('All accounts')),
                  for (final a in accounts) PopupMenuItem(value: a, child: Text(a)),
                ],
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Flexible(
                      child: Text(
                        account.isEmpty ? 'All accounts' : account,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(fontSize: 13, color: muted),
                      ),
                    ),
                    Icon(Icons.expand_more, size: 18, color: muted),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _pace(BuildContext context, SoFar pace) {
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    final p = context.palette;
    return Text.rich(
      TextSpan(
        style: TextStyle(fontSize: 13, color: muted),
        children: [
          TextSpan(text: pace.text),
          if (pace.change != null) ...[
            const TextSpan(text: ' ('),
            TextSpan(text: pace.change, style: TextStyle(color: pace.up ? p.serious : pace.down ? p.good : muted)),
            const TextSpan(text: ')'),
          ],
        ],
      ),
    );
  }

  Widget _summary(Totals now, Totals? was, bool has, String? cm, int waiting, SoFar? pace, String? left) {
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    final label = cm == null ? '' : monthName(cm);
    final delta = was == null ? null : (has ? deltaText(now.spend, was.spend, label) : 'No data for $label');
    return Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Headline(label: 'Spent', value: inr(now.spend), detail: delta),
                    if (pace != null) _pace(context, pace),
                    if (left != null) Text(left, style: TextStyle(fontSize: 13, color: Theme.of(context).colorScheme.onSurfaceVariant)),
                  ],
                ),
              ),
              PopupMenuButton<String>(
                tooltip: 'Compare with',
                initialValue: _compare,
                onSelected: (v) => setState(() => _compare = v),
                itemBuilder: (_) => const [
                  PopupMenuItem(value: 'prev', child: Text('Compare with previous month')),
                  PopupMenuItem(value: 'year', child: Text('Compare with same month last year')),
                  PopupMenuItem(value: 'none', child: Text('No comparison')),
                ],
                child: Padding(
                  padding: const EdgeInsets.all(4),
                  child: Icon(Icons.tune, size: 18, color: muted),
                ),
              ),
            ],
          ),
          const Padding(padding: EdgeInsets.symmetric(vertical: 12), child: Divider()),
          Row(
            children: [
              Expanded(
                child: Stat(label: 'Saved and invested', value: inr(now.saved)),
              ),
              Expanded(
                child: Stat(label: 'Waiting for review', value: '$waiting'),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _balances(Ledger led) {
    if (_balancesHidden) {
      return Padding(
        padding: const EdgeInsets.only(bottom: 4),
        child: Align(
          alignment: Alignment.centerLeft,
          child: TextButton(onPressed: () => _setBalancesHidden(false), child: const Text('Show account balances')),
        ),
      );
    }
    final scheme = Theme.of(context).colorScheme;
    final known = led.balances.where((b) => b.balance != null && b.inTotal).toList();
    final left = led.balances.where((b) => b.balance != null && !b.inTotal).length;
    final total = known.fold(0.0, (a, b) => a + b.balance!);
    return Panel(
      title: 'Account balances',
      trailing: _Link('Hide', () => _setBalancesHidden(true)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            inr(total),
            style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700, fontFeatures: figures),
          ),
          Text(
            'Across ${known.length} account${known.length == 1 ? '' : 's'}${left > 0 ? ', $left left out' : ''}',
            style: TextStyle(fontSize: 12.5, color: scheme.onSurfaceVariant),
          ),
          const SizedBox(height: 8),
          for (final b in led.balances)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 6),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(b.account, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w500)),
                        Text(_balanceNote(b), style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant)),
                      ],
                    ),
                  ),
                  Text(
                    b.balance == null ? 'Not set' : inr(b.balance!),
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                      fontFeatures: figures,
                      color: b.inTotal && b.balance != null ? null : scheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  String _balanceNote(Balance b) {
    if (b.balance == null) return 'No balance entered yet';
    final when = b.confirmedAt == null ? '' : ' ${dayLabel(b.confirmedAt!.toIso8601String().substring(0, 10))}';
    final since = (b.since ?? 0) > 0 ? '${b.since} since' : 'nothing since';
    final note = '${b.fromAlert ? 'Bank alert' : 'Confirmed'}$when · $since';
    return b.inTotal ? note : '$note · not in total';
  }

  Widget _review(List<Txn> waiting) {
    return Panel(
      title: 'To review',
      trailing: Tag('${waiting.length}'),
      note: 'Suggested categories. Approve these on the Mac dashboard.',
      child: ShowMore(first: 3, children: [for (final t in waiting) TxnRow(t, showDate: true)]),
    );
  }

  Widget _categories(Ledger led, Totals now, Totals? was, String month, String account) {
    final names = {...now.categories.keys, ...?was?.categories.keys};
    final rows = [
      for (final c in names) (name: c, a: now.categories[c] ?? 0.0, b: was?.categories[c] ?? 0.0),
    ].where((r) => r.a >= 1 || r.b >= 1).toList()..sort((x, y) => y.a.compareTo(x.a));
    final top = rows.fold<double>(1, (m, r) => math.max(m, math.max(r.a, r.b)));
    final scheme = Theme.of(context).colorScheme;
    final p = context.palette;
    return Panel(
      title: 'Spending by category',
      note: was == null ? null : 'Grey bar: ${monthName(shiftMonth(month, _compare == 'prev' ? -1 : -12))}',
      child: rows.isEmpty
          ? Text('No spending recorded for ${monthName(month)}.', style: TextStyle(color: scheme.onSurfaceVariant))
          : Column(
              children: [
                for (final r in rows)
                  InkWell(
                    borderRadius: BorderRadius.circular(8),
                    onTap: r.name == pendingLabel
                        ? null
                        : () => _openCategory(led, r.name, month, account, now.subs[r.name] ?? {}),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(vertical: 8),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Row(
                            children: [
                              Expanded(
                                child: Text(
                                  r.name,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: const TextStyle(fontSize: 14),
                                ),
                              ),
                              Text(
                                inr(r.a),
                                style: const TextStyle(
                                  fontSize: 14,
                                  fontWeight: FontWeight.w600,
                                  fontFeatures: figures,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 5),
                          Meter(value: r.a / top),
                          if (was != null) ...[
                            const SizedBox(height: 2),
                            Meter(value: r.b / top, color: p.compare, height: 3),
                          ],
                        ],
                      ),
                    ),
                  ),
              ],
            ),
    );
  }

  void _openCategory(Ledger led, String category, String month, String account, Map<String, double> subs) {
    final list = led.transactions
        .where((t) => t.category == category && !t.pending && txnInScope(t, month, account))
        .toList();
    final parts = subs.entries.toList()..sort((a, b) => b.value.compareTo(a.value));
    final showParts = parts.length > 1 || (parts.isNotEmpty && parts.first.key.isNotEmpty);
    final total = parts.fold(0.0, (a, e) => a + e.value);
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      builder: (_) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.65,
        maxChildSize: 0.92,
        builder: (context, controller) => ListView(
          controller: controller,
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
          children: [
            Headline(label: '$category · ${monthName(month)}', value: inr(total)),
            const SizedBox(height: 10),
            if (showParts)
              for (final e in parts)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 3),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(e.key.isEmpty ? 'No subcategory' : e.key, style: const TextStyle(fontSize: 13)),
                      ),
                      Text(inr(e.value), style: const TextStyle(fontSize: 13, fontFeatures: figures)),
                    ],
                  ),
                ),
            if (showParts) const Padding(padding: EdgeInsets.symmetric(vertical: 8), child: Divider()),
            for (final t in list) TxnRow(t, showDate: true),
          ],
        ),
      ),
    );
  }

  void _openDay(Ledger led, String month, String account, int day, double total) {
    final date = '$month-${day.toString().padLeft(2, '0')}';
    final list = spendingIn(led, month, account, noLoans: _noLoans).where((t) => t.date == date).toList();
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      builder: (_) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.65,
        maxChildSize: 0.92,
        builder: (context, controller) => ListView(
          controller: controller,
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
          children: [
            Headline(label: dayYearLabel(date), value: inr(total)),
            const SizedBox(height: 10),
            for (final t in list) TxnRow(t),
          ],
        ),
      ),
    );
  }

  Widget _days(Ledger led, String month, String account) {
    if (dailySpend(led, month, account).every((v) => v == 0)) return const SizedBox.shrink();
    final days = dailySpend(led, month, account, noLoans: _noLoans);
    final most = days.fold<double>(0, math.max);
    final top = math.max(1.0, most);
    final peak = days.indexOf(most);
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    final name = monthName(month).split(' ').first;
    return Panel(
      title: 'By day',
      note: most == 0 ? 'Nothing else this month.' : 'Highest ${inr(most)} on ${peak + 1} $name. Tap a bar for its transactions.',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              Text('Exclude loans', style: TextStyle(fontSize: 13, color: muted)),
              const SizedBox(width: 6),
              Switch(value: _noLoans, onChanged: (v) => setState(() => _noLoans = v)),
            ],
          ),
          SizedBox(
            height: 120,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                for (var i = 0; i < days.length; i++)
                  Expanded(
                    child: GestureDetector(
                      behavior: HitTestBehavior.opaque,
                      onTap: days[i] == 0 ? null : () => _openDay(led, month, account, i + 1, days[i]),
                      child: Container(
                        alignment: Alignment.bottomCenter,
                        padding: const EdgeInsets.symmetric(horizontal: 0.5),
                        child: FractionallySizedBox(
                          heightFactor: days[i] / top,
                          widthFactor: 1,
                          child: Container(
                            decoration: BoxDecoration(
                              color: Theme.of(context).colorScheme.primary,
                              borderRadius: const BorderRadius.vertical(top: Radius.circular(2)),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ),
          const Divider(height: 1),
          const SizedBox(height: 3),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              for (final d in [1, 10, 20, days.length]) Text('$d', style: TextStyle(fontSize: 11, color: muted, fontFeatures: figures)),
            ],
          ),
        ],
      ),
    );
  }

  Widget _trend(Ledger led, String month, String account, List<String> months) {
    final shown = months.length > 13 ? months.sublist(months.length - 13) : months;
    final values = [for (final m in shown) totalsFor(led, m, account).spend];
    final top = math.max(1.0, values.fold<double>(0, math.max));
    final p = context.palette;
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    return Panel(
      title: 'By month',
      child: SizedBox(
        height: 124,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            for (var i = 0; i < shown.length; i++)
              Expanded(
                child: Tooltip(
                  message: '${monthName(shown[i])}: ${inr(values[i])}',
                  child: InkWell(
                    onTap: () => setState(() => _month = shown[i]),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.end,
                      children: [
                        if (shown[i] == month)
                          FittedBox(
                            child: Text(shortInr(values[i]), style: TextStyle(fontSize: 10, color: muted)),
                          ),
                        const SizedBox(height: 2),
                        Align(
                          alignment: Alignment.bottomCenter,
                          child: Container(
                            width: 14,
                            height: math.max(2, 84 * values[i] / top),
                            decoration: BoxDecoration(
                              color: shown[i] == month ? p.series : p.seriesSoft,
                              borderRadius: const BorderRadius.vertical(top: Radius.circular(4)),
                            ),
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(monthName(shown[i])[0], style: TextStyle(fontSize: 10, color: muted)),
                      ],
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _transactions(Ledger led, String month, String account) {
    final q = _query.trim().toLowerCase();
    final list = led.transactions.where((t) => txnInScope(t, month, account, query: q)).toList();
    final scheme = Theme.of(context).colorScheme;
    final rows = <Widget>[];
    String? day;
    for (final t in list) {
      if (t.date != day) {
        day = t.date;
        rows.add(
          Padding(
            padding: const EdgeInsets.only(top: 10, bottom: 2),
            child: Text(
              dayLabel(t.date),
              style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: scheme.onSurfaceVariant),
            ),
          ),
        );
      }
      rows.add(TxnRow(t));
    }
    return Panel(
      title: 'Transactions',
      trailing: Text('${list.length}', style: TextStyle(fontSize: 13, color: scheme.onSurfaceVariant)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          TextField(
            decoration: const InputDecoration(
              prefixIcon: Icon(Icons.search, size: 20),
              hintText: 'Search payee or description',
            ),
            onChanged: (v) => setState(() => _query = v),
          ),
          if (list.isEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 12),
              child: Text('No transactions match.', style: TextStyle(color: scheme.onSurfaceVariant)),
            )
          else
            ShowMore(key: ValueKey('$month$account$q'), first: 10, children: rows),
        ],
      ),
    );
  }
}

class _Link extends StatelessWidget {
  const _Link(this.text, this.onTap);
  final String text;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Text(text, style: TextStyle(fontSize: 13, color: Theme.of(context).colorScheme.primary)),
    );
  }
}
