import 'package:flutter/material.dart';

import 'data.dart';
import 'money.dart';
import 'theme.dart';
import 'widgets.dart';

/// The Grocery tab, read-only. The Mac works out every figure; subcategories and item groups are changed there.
class GroceryView extends StatefulWidget {
  const GroceryView({super.key, required this.ledger});
  final Ledger ledger;

  @override
  State<GroceryView> createState() => _GroceryViewState();
}

class _GroceryViewState extends State<GroceryView> {
  String? _month;

  List<dynamic> _list(Map<String, dynamic> map, String key) => map[key] as List<dynamic>? ?? const [];
  double _money(Object? value) => (value as num? ?? 0).toDouble();
  String _rupees(Object? value) {
    final amount = _money(value);
    return amount == amount.roundToDouble() ? inr(amount) : '₹${amount.toStringAsFixed(2)}';
  }

  String _quantity(Map<String, dynamic> item) {
    final quantity = _money(item['quantity']);
    return item['unit'] == 'KG' ? '${quantity.toStringAsFixed(2)} kg' : '${quantity.round()}';
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final months = widget.ledger.groceryMonths.keys.toList()..sort();
    final problems = widget.ledger.groceryProblems;
    if (months.isEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(32),
        children: [
          Text('No groceries yet.', textAlign: TextAlign.center, style: TextStyle(color: scheme.onSurfaceVariant)),
        ],
      );
    }
    final month = months.contains(_month) ? _month! : months.last;
    final i = months.indexOf(month);
    final m = widget.ledger.groceryMonths[month]!;
    final total = _money(m['total']);
    final billed = _money(m['billed']);
    final before = i > 0 ? _money(widget.ledger.groceryMonths[months[i - 1]]!['total']) : 0.0;
    final subcategories = _list(m, 'subcategories').cast<Map<String, dynamic>>();
    final groups = _list(m, 'groups').cast<Map<String, dynamic>>();
    final items = _list(m, 'items').cast<Map<String, dynamic>>();
    final bills = _list(m, 'bills').cast<Map<String, dynamic>>();

    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: pagePadding,
      children: [
        Padding(
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
        ),
        if (problems.isNotEmpty)
          Panel(
            title: 'Needs attention',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [for (final p in problems) Text(p, style: TextStyle(fontSize: 13, color: scheme.onSurfaceVariant))],
            ),
          ),
        Panel(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Headline(
                label: 'Groceries',
                value: inr(total),
                detail: before > 0 ? deltaText(total, before, monthName(months[i - 1])) : null,
              ),
              const Padding(padding: EdgeInsets.symmetric(vertical: 12), child: Divider()),
              Row(
                children: [
                  Expanded(child: Stat(label: 'Detailed by bills', value: inr(billed))),
                  Expanded(child: Stat(label: 'Bills', value: '${bills.length}')),
                ],
              ),
            ],
          ),
        ),
        if (subcategories.isNotEmpty) Panel(title: 'By subcategory', child: _bars(subcategories)),
        if (groups.isNotEmpty) Panel(title: 'By item group', child: _bars(groups)),
        if (items.isNotEmpty)
          Panel(
            title: 'Items',
            trailing: Text('${items.length}', style: TextStyle(fontSize: 13, color: scheme.onSurfaceVariant)),
            child: ShowMore(first: 8, children: [for (final item in items) _item(item)]),
          ),
        if (bills.isNotEmpty)
          Panel(
            title: 'Bills',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [for (final bill in bills) _bill(bill)],
            ),
          ),
      ],
    );
  }

  Widget _bars(List<Map<String, dynamic>> rows) {
    final top = rows.fold<double>(1, (m, r) => _money(r['amount']) > m ? _money(r['amount']) : m);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final r in rows)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 7),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(
                  children: [
                    Expanded(child: Text(r['name'] as String, style: const TextStyle(fontSize: 14))),
                    Text(inr(_money(r['amount'])),
                        style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, fontFeatures: figures)),
                  ],
                ),
                if (r['payees'] != null)
                  Text(_list(r, 'payees').join(', '), maxLines: 1, overflow: TextOverflow.ellipsis,
                      style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.onSurfaceVariant)),
                const SizedBox(height: 5),
                Meter(value: _money(r['amount']) / top),
              ],
            ),
          ),
      ],
    );
  }

  Widget _item(Map<String, dynamic> item) {
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    final p = context.palette;
    final prices = _list(item, 'history').map((h) => _money((h as Map<String, dynamic>)['price'])).toList();
    final first = prices.isEmpty ? 0.0 : prices.first;
    final last = prices.isEmpty ? 0.0 : prices.last;
    final change = first == 0 ? 0.0 : (last - first) / first * 100;
    final moved = prices.length > 1 && change.abs() >= 0.5;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 7),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(item['name'] as String, maxLines: 1, overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w500)),
              ),
              Text(inr(_money(item['amount'])),
                  style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, fontFeatures: figures)),
            ],
          ),
          Row(
            children: [
              Expanded(
                child: Text('${item['group']} · ${_quantity(item)} · ${prices.map(_rupees).join(' → ')}',
                    maxLines: 2, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 12, color: muted)),
              ),
              if (moved)
                Text('${change > 0 ? '▲' : '▼'} ${change.abs().toStringAsFixed(0)}%',
                    style: TextStyle(fontSize: 12, color: change > 0 ? p.serious : p.good)),
            ],
          ),
        ],
      ),
    );
  }

  Widget _bill(Map<String, dynamic> bill) {
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    final lines = _list(bill, 'items').length;
    return InkWell(
      onTap: () => _openBill(bill),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('${dayLabel(bill['date'] as String)} · ${bill['source']}', style: const TextStyle(fontSize: 14)),
                  Text('$lines item${lines == 1 ? '' : 's'}', style: TextStyle(fontSize: 12, color: muted)),
                ],
              ),
            ),
            if (bill['matched'] != true) ...[const Tag('no payment found'), const SizedBox(width: 8)],
            Text(_rupees(bill['total']),
                style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, fontFeatures: figures)),
          ],
        ),
      ),
    );
  }

  void _openBill(Map<String, dynamic> bill) {
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
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
            Headline(label: '${bill['source']} · ${dayYearLabel(bill['date'] as String)}', value: _rupees(bill['total'])),
            const SizedBox(height: 10),
            for (final raw in _list(bill, 'items'))
              Builder(builder: (context) {
                final line = raw as Map<String, dynamic>;
                return Padding(
                  padding: const EdgeInsets.symmetric(vertical: 6),
                  child: Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(line['name'] as String, style: const TextStyle(fontSize: 14)),
                            Text('${_quantity(line)} at ${_rupees(line['price'])}', style: TextStyle(fontSize: 12, color: muted)),
                          ],
                        ),
                      ),
                      Text(_rupees(line['amount']), style: const TextStyle(fontSize: 14, fontFeatures: figures)),
                    ],
                  ),
                );
              }),
          ],
        ),
      ),
    );
  }
}
