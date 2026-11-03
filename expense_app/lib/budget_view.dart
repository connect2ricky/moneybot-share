import 'package:flutter/material.dart';

import 'data.dart';
import 'money.dart';
import 'theme.dart';
import 'widgets.dart';

/// This month's budgets against what has been spent in each category. Budgets are set on the Mac dashboard.
class BudgetView extends StatefulWidget {
  const BudgetView({super.key, required this.ledger});
  final Ledger ledger;

  @override
  State<BudgetView> createState() => _BudgetViewState();
}

class _BudgetViewState extends State<BudgetView> {
  late String _month = monthKey(DateTime.now());

  Widget _monthBar(String first, String last) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          IconButton(
            tooltip: 'Previous month',
            visualDensity: VisualDensity.compact,
            onPressed: _month.compareTo(first) > 0 ? () => setState(() => _month = shiftMonth(_month, -1)) : null,
            icon: const Icon(Icons.chevron_left),
          ),
          Text(monthName(_month), style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
          IconButton(
            tooltip: 'Next month',
            visualDensity: VisualDensity.compact,
            onPressed: _month.compareTo(last) < 0 ? () => setState(() => _month = shiftMonth(_month, 1)) : null,
            icon: const Icon(Icons.chevron_right),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final current = monthKey(DateTime.now());
    final dated = monthsWithGaps(widget.ledger.transactions);
    final first = dated.isEmpty ? current : dated.first;
    final last = shiftMonth(current, 12);
    final bar = _monthBar(first, last);
    final rows = budgetRows(widget.ledger, _month);
    if (rows.isEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: pagePadding,
        children: [
          bar,
          Panel(
            child: Text('Nothing for ${monthName(_month)} yet. Budgets are set on the Mac dashboard.',
                style: TextStyle(color: scheme.onSurfaceVariant)),
          ),
        ],
      );
    }
    final budgeted = rows.where((r) => r.hasBudget).toList();
    final allocated = budgeted.fold(0.0, (a, r) => a + r.budget);
    final used = budgeted.fold(0.0, (a, r) => a + r.spent);
    final unbudgeted = rows.where((r) => !r.hasBudget).fold(0.0, (a, r) => a + r.spent);
    final left = allocated - used;
    final over = left < 0;
    final p = context.palette;
    final mandatory = rows.where((r) => r.mandatory).toList();
    final normal = rows.where((r) => !r.mandatory).toList();

    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: pagePadding,
      children: [
        bar,
        Panel(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Headline(
                label: over ? 'Over budget' : 'Left to spend',
                value: inr(left.abs()),
                color: over ? p.serious : null,
                detail: '${inr(used)} spent of ${inr(allocated)}',
              ),
              const SizedBox(height: 10),
              Meter(value: allocated == 0 ? 0 : used / allocated, color: over ? p.serious : null, height: 8),
              const Padding(padding: EdgeInsets.symmetric(vertical: 12), child: Divider()),
              Row(
                children: [
                  Expanded(child: Stat(label: 'Used', value: allocated == 0 ? '—' : '${(used / allocated * 100).round()}%')),
                  Expanded(child: Stat(label: 'Without a budget', value: inr(unbudgeted))),
                ],
              ),
            ],
          ),
        ),
        if (mandatory.isNotEmpty) _group(context, 'Mandatory', mandatory),
        if (normal.isNotEmpty) _group(context, 'Normal', normal),
        Panel(title: 'Total of all', child: _total(context, rows)),
      ],
    );
  }

  Widget _group(BuildContext context, String title, List<BudgetRow> rows) {
    return Panel(
      title: title,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final r in rows) _row(context, r),
          const Padding(padding: EdgeInsets.only(top: 6, bottom: 10), child: Divider()),
          _total(context, rows),
        ],
      ),
    );
  }

  Widget _row(BuildContext context, BudgetRow r) {
    final scheme = Theme.of(context).colorScheme;
    final p = context.palette;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 7),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(child: Text(r.name, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 14))),
              Text(inr(r.spent), style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, fontFeatures: figures)),
              if (r.hasBudget)
                Text(' / ${inr(r.budget)}', style: TextStyle(fontSize: 12.5, color: scheme.onSurfaceVariant, fontFeatures: figures)),
            ],
          ),
          if (r.hasBudget) ...[
            const SizedBox(height: 5),
            Meter(value: r.spent / r.budget, color: r.over ? p.serious : null),
            const SizedBox(height: 3),
            Text(
              r.over ? 'Over by ${inr(-r.left)}' : '${inr(r.left)} left',
              style: TextStyle(fontSize: 12, color: r.over ? p.serious : scheme.onSurfaceVariant),
            ),
          ] else
            Text('No budget', style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant)),
        ],
      ),
    );
  }

  /// Left only counts categories that have a budget, as on the dashboard.
  Widget _total(BuildContext context, List<BudgetRow> rows) {
    final alloc = rows.fold(0.0, (a, r) => a + r.budget);
    final spent = rows.fold(0.0, (a, r) => a + r.spent);
    final onBudget = rows.where((r) => r.hasBudget).fold(0.0, (a, r) => a + r.spent);
    final left = alloc - onBudget;
    final over = alloc > 0 && left < 0;
    return Row(
      children: [
        Expanded(child: Stat(label: 'Budget', value: alloc == 0 ? '—' : inr(alloc))),
        Expanded(child: Stat(label: 'Spent', value: inr(spent))),
        Expanded(
          child: Stat(
            label: over ? 'Over' : 'Left',
            value: alloc == 0 ? '—' : inr(left.abs()),
            color: over ? context.palette.serious : null,
          ),
        ),
      ],
    );
  }
}
