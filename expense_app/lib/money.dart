import 'dart:math' as math;

import 'data.dart';

const _monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// ---- Formatting: the same rules as the dashboard ----

/// Rupees with Indian grouping, for example ₹1,00,23,785.
String inr(num value) {
  final n = value.round();
  final digits = n.abs().toString();
  var grouped = digits;
  if (digits.length > 3) {
    var rest = digits.substring(0, digits.length - 3);
    final groups = <String>[];
    while (rest.length > 2) {
      groups.insert(0, rest.substring(rest.length - 2));
      rest = rest.substring(0, rest.length - 2);
    }
    if (rest.isNotEmpty) groups.insert(0, rest);
    grouped = '${groups.join(',')},${digits.substring(digits.length - 3)}';
  }
  return '${n < 0 ? '−' : ''}₹$grouped';
}

/// Short form for chart labels: ₹5k, ₹1.2L.
String shortInr(num value) {
  final a = value.abs();
  if (a >= 1e5) return '₹${(a / 1e5).toStringAsFixed(a >= 1e6 ? 0 : 1)}L';
  if (a >= 1e3) return '₹${(a / 1e3).round()}k';
  return '₹${a.round()}';
}

String monthName(String month) {
  final m = int.parse(month.substring(5, 7));
  return '${_monthNames[m - 1]} ${month.substring(0, 4)}';
}

/// "21 Oct" for a YYYY-MM-DD date.
String dayLabel(String date) {
  final m = int.parse(date.substring(5, 7));
  return '${date.substring(8)} ${_monthNames[m - 1]}';
}

/// "21 Oct, 3:04 pm" for a moment in time.
String whenLabel(DateTime d) {
  final hour = d.hour % 12 == 0 ? 12 : d.hour % 12;
  return '${d.day} ${_monthNames[d.month - 1]}, $hour:${d.minute.toString().padLeft(2, '0')} ${d.hour < 12 ? 'am' : 'pm'}';
}

String dayYearLabel(String date) => '${dayLabel(date)} ${date.substring(0, 4)}';

String monthKey(DateTime d) => '${d.year}-${d.month.toString().padLeft(2, '0')}';

String shiftMonth(String month, int by) {
  final y = int.parse(month.substring(0, 4));
  final m = int.parse(month.substring(5, 7));
  return monthKey(DateTime(y, m + by));
}

/// Every month from the first transaction to the last, oldest first, with gaps filled.
List<String> monthsWithGaps(List<Txn> transactions) {
  if (transactions.isEmpty) return [];
  final seen = transactions.map((t) => t.date.substring(0, 7)).toSet().toList()..sort();
  final out = <String>[];
  var m = seen.first;
  while (m.compareTo(seen.last) <= 0) {
    out.add(m);
    m = shiftMonth(m, 1);
  }
  return out;
}

String deltaText(double now, double before, String label) {
  if (before == 0) return 'no data for $label';
  final pct = (now - before) / before.abs() * 100;
  final arrow = pct > 0.5 ? '▲' : pct < -0.5 ? '▼' : '•';
  return '$arrow ${pct.abs().toStringAsFixed(0)}% vs $label (${inr(before)})';
}

// ---- Spending ----

class Totals {
  double spend = 0;
  double saved = 0;
  double pending = 0;
  int count = 0;
  final Map<String, double> categories = {};
  final Map<String, Map<String, double>> subs = {};
}

bool _inAccount(Txn t, String account) => account.isEmpty || t.account == account;

/// What the dashboard counts for one month. Transfers and money received are left out of spending.
/// [upToDay] stops at that day of the month, to compare with a month still under way.
Totals totalsFor(Ledger ledger, String month, String account, {int upToDay = 31}) {
  final r = Totals();
  for (final t in ledger.transactions) {
    if (!t.counted || t.credit || !_inAccount(t, account) || !t.date.startsWith(month)) continue;
    if (int.parse(t.date.substring(8)) > upToDay) continue;
    r.count++;
    final group = ledger.categories[t.category] ?? 'expense';
    if (t.pending) {
      if (group == 'expense') {
        r.spend += t.amount;
        r.pending += t.amount;
      }
      continue;
    }
    if (group == 'expense') {
      r.spend += t.amount;
      r.categories[t.category] = (r.categories[t.category] ?? 0) + t.amount;
      final sub = r.subs.putIfAbsent(t.category, () => {});
      final name = t.subcategory ?? '';
      sub[name] = (sub[name] ?? 0) + t.amount;
    } else if (group == 'savings') {
      r.saved += t.amount;
    }
  }
  if (r.pending > 0) r.categories[pendingLabel] = r.pending;
  return r;
}

/// One amount per day of [month], counted as the Spent figure counts, so they add up to it.
List<double> dailySpend(Ledger ledger, String month, String account, {bool noLoans = false}) {
  final parts = month.split('-').map(int.parse).toList();
  final days = List<double>.filled(DateTime(parts[0], parts[1] + 1, 0).day, 0);
  for (final t in spendingIn(ledger, month, account, noLoans: noLoans)) {
    days[int.parse(t.date.substring(8)) - 1] += t.amount;
  }
  return days;
}

/// The transactions counted as spending in [month].
Iterable<Txn> spendingIn(Ledger ledger, String month, String account, {bool noLoans = false}) => ledger.transactions.where((t) =>
    t.counted && !t.credit && _inAccount(t, account) && t.date.startsWith(month) &&
    !(noLoans && t.category == 'Loan EMI') &&
    (ledger.categories[t.category] ?? 'expense') == 'expense');

class SoFar {
  const SoFar(this.text, {this.change, this.up = false, this.down = false});
  final String text;
  final String? change;
  final bool up;
  final bool down;
}

/// How the running month compares with the same days of last month, or null for a month already over.
SoFar? soFar(Ledger ledger, String month, String account, double spent, DateTime today) {
  if (month != monthKey(today)) return null;
  final then = totalsFor(ledger, shiftMonth(month, -1), account, upToDay: today.day).spend;
  final text = 'At this time last month ${inr(then)}';
  if (then == 0) return SoFar(text);
  final pct = (spent - then) / then * 100;
  final arrow = pct > 0.5 ? '▲' : pct < -0.5 ? '▼' : '•';
  return SoFar(text, change: '$arrow ${pct.abs().toStringAsFixed(0)}%', up: pct > 0.5, down: pct < -0.5);
}

/// Salary received in [month] less what was spent. Salary reaches one account, so it needs all accounts in view.
String? leftLine(Ledger ledger, String month, String account, double spent) {
  if (account.isNotEmpty) return null;
  final salary = ledger.transactions
      .where((t) => t.category == 'Salary' && t.credit && t.date.startsWith(month))
      .fold(0.0, (a, t) => a + t.amount);
  return salary == 0 ? 'No salary this month yet' : 'Left from salary ${inr(salary - spent)}';
}

bool txnInScope(Txn t, String month, String account, {String query = ''}) {
  if (!t.date.startsWith(month) || !_inAccount(t, account)) return false;
  if (query.isEmpty) return true;
  return '${t.payee} ${t.note ?? ''}'.toLowerCase().contains(query);
}

/// The tag shown next to a payee, as on the dashboard.
String? txnTag(Txn t) {
  if (!t.counted) return 'not counted';
  if (t.credit) return 'received, not counted';
  if (t.pending) return 'pending';
  return null;
}

// ---- Loans: the same rules as the loans page ----

bool loanActive(Loan l, String month) => l.firstMonth.compareTo(month) <= 0 && month.compareTo(l.lastMonth) <= 0;

/// Inclusive number of months from [a] to [b], zero when [a] is after [b].
int monthCount(String a, String b) {
  if (a.compareTo(b) > 0) return 0;
  final years = int.parse(b.substring(0, 4)) - int.parse(a.substring(0, 4));
  final months = int.parse(b.substring(5, 7)) - int.parse(a.substring(5, 7));
  return years * 12 + months + 1;
}

/// EMIs still to pay from this month on; this month drops out once it is ticked as paid.
int loanLeft(Loan l, Ledger ledger, String now) {
  final start = l.firstMonth.compareTo(now) > 0 ? l.firstMonth : now;
  final paidNow = loanActive(l, now) && ledger.isPaid(l, now) ? 1 : 0;
  return monthCount(start, l.lastMonth) - paidNow;
}

/// Principal still owed: the remaining EMIs discounted at the loan's monthly rate. Null when the rate is unknown.
double? loanPreclose(Loan l, Ledger ledger, String now) {
  if (l.rate == null) return null;
  final n = loanLeft(l, ledger, now);
  final i = l.rate! / 1200;
  if (i == 0) return n * l.emi;
  return l.emi * (1 - math.pow(1 + i, -n)) / i;
}

double emiIn(Ledger ledger, String month) =>
    ledger.loans.where((l) => loanActive(l, month)).fold(0.0, (a, l) => a + l.emi);

// ---- Budget: the same spent numbers as the Spending page, for the current month ----

class BudgetRow {
  const BudgetRow(this.name, this.budget, this.spent, {this.mandatory = false});
  final String name;
  final double budget;
  final double spent;
  final bool mandatory;

  bool get hasBudget => budget > 0;
  double get left => budget - spent;
  bool get over => hasBudget && spent > budget;
}

/// Spending categories with a transaction in [month], any budget, or a place on the budget page's own list.
/// Budgeted ones come first.
List<BudgetRow> budgetRows(Ledger led, String month) {
  final spent = totalsFor(led, month, '').categories;
  final active = {for (final t in led.transactions) if (t.date.startsWith(month)) t.category};
  final rows = [
    for (final e in led.categories.entries)
      if (e.value == 'expense' &&
          (active.contains(e.key) || led.budgetCategories.contains(e.key) ||
              (led.budgets[e.key] ?? 0) > 0 || led.budgetFor(e.key, month) > 0))
        BudgetRow(e.key, led.budgetFor(e.key, month), spent[e.key] ?? 0, mandatory: led.mandatory.contains(e.key)),
  ];
  rows.sort((a, b) {
    if (a.hasBudget != b.hasBudget) return a.hasBudget ? -1 : 1;
    final bySpent = b.spent.compareTo(a.spent);
    return bySpent != 0 ? bySpent : a.name.compareTo(b.name);
  });
  return rows;
}
