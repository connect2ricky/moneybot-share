import 'package:flutter/material.dart';

import 'data.dart';
import 'money.dart';
import 'theme.dart';
import 'widgets.dart';

/// Credit card statements, read-only and separate from spending and budgets.
class CardsView extends StatefulWidget {
  const CardsView({super.key, required this.ledger});
  final Ledger ledger;

  @override
  State<CardsView> createState() => _CardsViewState();
}

class _CardsViewState extends State<CardsView> {
  String? _month;

  String _rupees(double amount) => '${amount < 0 ? '−' : ''}₹${amount.abs().toStringAsFixed(2)}';

  Widget _monthBar(List<String> months, String month) {
    final i = months.indexOf(month);
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
          Text(monthName(month), style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
          IconButton(
            tooltip: 'Next month',
            visualDensity: VisualDensity.compact,
            onPressed: i < months.length - 1 ? () => setState(() => _month = months[i + 1]) : null,
            icon: const Icon(Icons.chevron_right),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final led = widget.ledger;
    final problems = [
      if (led.cardProblems.isNotEmpty)
        Panel(
          title: 'Could not be read',
          child: Text(led.cardProblems.join('\n'), style: TextStyle(fontSize: 13, color: context.palette.serious)),
        ),
    ];
    final months = {for (final s in led.cardStatements) s.month}.toList()..sort();
    if (months.isEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(32),
        children: [
          ...problems,
          Text('No card statements yet.', textAlign: TextAlign.center, style: TextStyle(color: scheme.onSurfaceVariant)),
        ],
      );
    }
    final month = months.contains(_month) ? _month! : months.last;
    final list = led.cardStatements.where((s) => s.month == month).toList();
    final total = list.fold(0.0, (a, s) => a + s.totalDue);
    final least = list.fold(0.0, (a, s) => a + s.minDue);
    final emiTotal = list.fold(0.0, (a, s) => a + s.emiTotal);
    final others = [
      for (final s in list)
        for (final r in s.rows)
          if (!r.emi && !r.payment) (card: s.card, row: r),
    ]..sort((a, b) => b.row.date.compareTo(a.row.date));
    final emiCount = list.fold(0, (a, s) => a + s.emis.where((e) => e.principal > 0).length);

    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: pagePadding,
      children: [
        _monthBar(months, month),
        Panel(
          child: Headline(
            label: 'Total due',
            value: _rupees(total),
            detail: '${_rupees(least)} minimum · ${_rupees(emiTotal)} in $emiCount EMI${emiCount == 1 ? '' : 's'}',
          ),
        ),
        ...problems,
        for (final s in list) _statement(context, s),
        if (others.isNotEmpty)
          Panel(
            title: 'Other expenses',
            note: 'Everything except EMIs, GST and your bill payments.',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                ShowMore(first: 6, children: [for (final o in others) _row(context, o.row, card: o.card)]),
                const Divider(),
                Text('Total ${_rupees(others.fold(0.0, (a, o) => a + (o.row.credit ? -o.row.amount : o.row.amount)))}',
                    textAlign: TextAlign.right, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600, fontFeatures: figures)),
              ],
            ),
          ),
      ],
    );
  }

  Widget _statement(BuildContext context, CardStatement s) {
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    final used = s.creditLimit - s.available;
    return Panel(
      title: '${s.card} …${s.last4}',
      trailing: s.balanced ? null : const Tag('check figures'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(child: Stat(label: 'Total due', value: _rupees(s.totalDue))),
              Expanded(child: Stat(label: 'EMIs', value: _rupees(s.emiTotal), detail: s.emis.where((e) => e.number != null).map((e) => e.label).join(' · '))),
              Expanded(child: Stat(label: 'Others', value: _rupees(s.others))),
            ],
          ),
          const SizedBox(height: 8),
          Text('Statement ${dayYearLabel(s.statementDate)} · due ${dayYearLabel(s.dueDate)}',
              style: TextStyle(fontSize: 12, color: muted)),
          const SizedBox(height: 8),
          Meter(value: s.creditLimit == 0 ? 0 : used / s.creditLimit),
          const SizedBox(height: 3),
          Text('${_rupees(used)} of ${_rupees(s.creditLimit)} limit in use', style: TextStyle(fontSize: 12, color: muted)),
          if (s.emis.isNotEmpty) ...[
            const SizedBox(height: 10),
            const Text('EMIs', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
            for (final e in s.emis) _emi(context, e),
          ],
          if (s.rows.isNotEmpty) ...[
            const SizedBox(height: 8),
            ShowMore(first: 3, children: [for (final r in s.rows) _row(context, r)]),
          ],
        ],
      ),
    );
  }

  Widget _emi(BuildContext context, CardEmi e) {
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    final left = e.left == null ? '' : e.left == 0 ? ' · last one' : ' · ${e.left} left';
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(e.name, style: const TextStyle(fontSize: 13)),
                Text(e.number == null ? '' : '${e.label}$left · ${_rupees(e.interest)} interest · ${_rupees(e.gst)} GST',
                    style: TextStyle(fontSize: 12, color: muted)),
              ],
            ),
          ),
          const SizedBox(width: 8),
          Text(_rupees(e.amount), style: const TextStyle(fontSize: 13, fontFeatures: figures)),
        ],
      ),
    );
  }

  Widget _row(BuildContext context, CardRow r, {String? card}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(width: 52, child: Text(dayLabel(r.date), style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.onSurfaceVariant))),
          Expanded(
            child: Text(card != null ? '$card · ${r.label}' : r.emi ? 'EMI · ${r.details}' : r.details,
                style: const TextStyle(fontSize: 13)),
          ),
          const SizedBox(width: 8),
          Text('${r.credit ? '−' : ''}${_rupees(r.amount)}',
              style: TextStyle(fontSize: 13, fontFeatures: figures, color: r.credit ? context.palette.good : null)),
        ],
      ),
    );
  }
}
