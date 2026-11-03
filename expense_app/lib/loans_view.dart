import 'package:flutter/material.dart';

import 'data.dart';
import 'money.dart';
import 'theme.dart';
import 'widgets.dart';

/// The loans page, read-only: this month's EMIs and the schedule. Ticks and edits are made on the Mac.
class LoansView extends StatelessWidget {
  const LoansView({super.key, required this.ledger});
  final Ledger ledger;

  @override
  Widget build(BuildContext context) {
    final led = ledger;
    final scheme = Theme.of(context).colorScheme;
    final now = monthKey(DateTime.now());
    if (led.loans.isEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(32),
        children: [Text('No loans yet.', textAlign: TextAlign.center, style: TextStyle(color: scheme.onSurfaceVariant))],
      );
    }
    final open = led.loans.where((l) => l.lastMonth.compareTo(now) >= 0).toList();
    final counted = open.where((l) => !l.separate).toList();
    final apart = open.where((l) => l.separate).toList();
    final closed = led.loans.where((l) => l.lastMonth.compareTo(now) < 0).toList();
    final due = led.loans.where((l) => loanActive(l, now)).toList()
      ..sort((a, b) {
        final byPaid = (led.isPaid(a, now) ? 1 : 0) - (led.isPaid(b, now) ? 1 : 0);
        return byPaid != 0 ? byPaid : b.emi.compareTo(a.emi);
      });
    final thisMonth = emiIn(led, now);
    final paid = due.where((l) => led.isPaid(l, now)).fold(0.0, (a, l) => a + l.emi);
    final remaining = counted.fold(0.0, (a, l) => a + loanLeft(l, led, now) * l.emi);
    final preclose = counted.fold(0.0, (a, l) => a + (loanPreclose(l, led, now) ?? 0));
    final next = open.where((l) => loanLeft(l, led, now) > 0).toList()
      ..sort((a, b) => a.lastMonth.compareTo(b.lastMonth));
    final later = shiftMonth(now, 12);
    final lenders = counted.map((l) => l.lender).toSet();

    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: pagePadding,
      children: [
        Panel(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Headline(
                label: 'EMI · ${monthName(now)}',
                value: inr(thisMonth),
                detail: '${inr(paid)} paid · ${inr(thisMonth - paid)} still due',
              ),
              const SizedBox(height: 10),
              Meter(value: thisMonth == 0 ? 0 : paid / thisMonth, color: context.palette.good, height: 8),
              const Padding(padding: EdgeInsets.symmetric(vertical: 12), child: Divider()),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(child: Stat(label: 'Left to pay', value: inr(remaining))),
                  Expanded(child: Stat(label: 'To preclose now', value: inr(preclose), detail: 'estimate')),
                ],
              ),
              const SizedBox(height: 12),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Stat(
                      label: 'Next to finish',
                      value: next.isEmpty ? '—' : next.first.name,
                      detail: next.isEmpty ? null : '${monthName(next.first.lastMonth)} · frees ${inr(next.first.emi)}',
                    ),
                  ),
                  Expanded(child: Stat(label: 'EMI a year from now', value: inr(emiIn(led, later)), detail: monthName(later))),
                ],
              ),
            ],
          ),
        ),
        if (due.isNotEmpty)
          Panel(
            title: 'Due this month',
            note: 'Tick EMIs as paid on the Mac.',
            child: ShowMore(first: 5, children: [for (final l in due) _due(context, l, now)]),
          ),
        for (final lender in lenders)
          Panel(
            title: lender,
            trailing: Text(
              '${inr(counted.where((l) => l.lender == lender && loanActive(l, now)).fold(0.0, (a, l) => a + l.emi))} a month',
              style: TextStyle(fontSize: 13, color: scheme.onSurfaceVariant, fontFeatures: figures),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                for (final l in counted.where((l) => l.lender == lender).toList()
                  ..sort((a, b) => a.lastMonth.compareTo(b.lastMonth)))
                  _loan(context, l, now),
              ],
            ),
          ),
        if (apart.isNotEmpty)
          Panel(
            title: 'Tracked separately',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [for (final l in apart) _loan(context, l, now)],
            ),
          ),
        if (closed.isNotEmpty)
          Panel(
            title: 'Closed',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [for (final l in closed) _loan(context, l, now)],
            ),
          ),
      ],
    );
  }

  Widget _due(BuildContext context, Loan l, String now) {
    final scheme = Theme.of(context).colorScheme;
    final done = ledger.isPaid(l, now);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          Icon(
            done ? Icons.check_circle : Icons.radio_button_unchecked,
            size: 20,
            color: done ? context.palette.good : context.palette.faint,
            semanticLabel: done ? 'Paid' : 'Not paid',
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(l.name, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 14)),
                Text(l.lender, style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant)),
              ],
            ),
          ),
          Text(inr(l.emi), style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, fontFeatures: figures)),
        ],
      ),
    );
  }

  Widget _loan(BuildContext context, Loan l, String now) {
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    final closed = l.lastMonth.compareTo(now) < 0;
    final left = loanLeft(l, ledger, now);
    final pre = loanPreclose(l, ledger, now);
    final tag = closed ? 'closed' : left == 0 ? 'paid off' : l.firstMonth.compareTo(now) > 0 ? 'starts ${monthName(l.firstMonth)}' : null;
    final facts = [
      if (!closed) '$left EMI${left == 1 ? '' : 's'} left',
      'ends ${monthName(l.lastMonth)}',
      if (l.rate != null) '${l.rate}%',
    ].join(' · ');
    final money = closed ? null : [
      '${inr(left * l.emi)} to pay',
      if (pre != null) 'preclose ${inr(pre)}',
    ].join(' · ');
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 7),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(l.name, maxLines: 1, overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w500)),
              ),
              if (tag != null) ...[Tag(tag), const SizedBox(width: 8)],
              Text(inr(l.emi), style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, fontFeatures: figures)),
            ],
          ),
          Text(facts, style: TextStyle(fontSize: 12, color: muted)),
          if (money != null) Text(money, style: TextStyle(fontSize: 12, color: muted)),
          if ((l.note ?? '').isNotEmpty) Text(l.note!, style: TextStyle(fontSize: 12, color: muted)),
        ],
      ),
    );
  }
}
