/// The dashboard's data as the Mac sends it. The phone only reads it.
library;

import 'dart:convert';

const pendingLabel = 'Pending review';
const uncategorised = 'Uncategorised';

bool _flag(Object? value) => value == true || (value is num && value != 0);

class Txn {
  const Txn({
    required this.key,
    required this.date,
    required this.account,
    required this.credit,
    required this.amount,
    required this.payee,
    required this.channel,
    required this.app,
    required this.category,
    required this.subcategory,
    required this.pending,
    required this.approved,
    required this.counted,
    required this.note,
  });

  final String key;
  final String date; // YYYY-MM-DD
  final String account;
  final bool credit;
  final double amount;
  final String payee;
  final String channel;
  final String? app;
  final String category;
  final String? subcategory;
  final bool pending;
  final bool approved;
  final bool counted;
  final String? note;

  factory Txn.fromJson(Map<String, dynamic> j) {
    final status = j['status'] as String?;
    return Txn(
      key: j['key'] as String,
      date: j['date'] as String,
      account: (j['account'] as String?) ?? '',
      credit: j['direction'] == 'credit',
      amount: (j['amount'] as num).toDouble(),
      payee: (j['payee'] as String?) ?? '',
      channel: (j['channel'] as String?) ?? '',
      app: j['app'] as String?,
      category: (j['category'] as String?) ?? uncategorised,
      subcategory: j['subcategory'] as String?,
      pending: status == 'pending',
      approved: status == 'approved',
      counted: _flag(j['counted']),
      note: j['note'] as String?,
    );
  }
}

class Balance {
  const Balance({
    required this.account,
    required this.balance,
    required this.inTotal,
    required this.fromAlert,
    required this.confirmed,
    required this.confirmedAt,
    required this.since,
  });

  final String account;
  final double? balance;
  final bool inTotal;
  final bool fromAlert;
  final double? confirmed;
  final DateTime? confirmedAt;
  final int? since;

  factory Balance.fromJson(Map<String, dynamic> j) {
    final ts = j['confirmed_ts'] as num?;
    return Balance(
      account: (j['account'] as String?) ?? '',
      balance: (j['balance'] as num?)?.toDouble(),
      inTotal: _flag(j['in_total']),
      fromAlert: j['source'] == 'alert',
      confirmed: (j['confirmed'] as num?)?.toDouble(),
      confirmedAt: ts == null ? null : DateTime.fromMillisecondsSinceEpoch(ts.toInt() * 1000),
      since: (j['since'] as num?)?.toInt(),
    );
  }
}

class Loan {
  const Loan({
    required this.id,
    required this.lender,
    required this.name,
    required this.principal,
    required this.rate,
    required this.emi,
    required this.firstMonth,
    required this.lastMonth,
    required this.note,
    required this.separate,
  });

  final int id;
  final String lender;
  final String name;
  final double? principal;
  final double? rate;
  final double emi;
  final String firstMonth; // YYYY-MM
  final String lastMonth;
  final String? note;
  final bool separate;

  factory Loan.fromJson(Map<String, dynamic> j) => Loan(
        id: (j['id'] as num).toInt(),
        lender: (j['lender'] as String?) ?? 'Other',
        name: (j['name'] as String?) ?? '',
        principal: (j['principal'] as num?)?.toDouble(),
        rate: (j['rate'] as num?)?.toDouble(),
        emi: (j['emi'] as num).toDouble(),
        firstMonth: j['first_month'] as String,
        lastMonth: j['last_month'] as String,
        note: j['note'] as String?,
        separate: _flag(j['separate']),
      );
}

class CardRow {
  const CardRow({required this.date, required this.details, required this.amount, required this.credit, required this.emi, required this.payment, required this.label});

  final String date; // YYYY-MM-DD
  final String details;
  final double amount;
  final bool credit;
  final bool emi;
  final bool payment;
  final String label;

  factory CardRow.fromJson(Map<String, dynamic> j) => CardRow(
        date: j['date'] as String,
        details: j['details'] as String,
        amount: (j['amount'] as num).toDouble(),
        credit: _flag(j['credit']),
        emi: _flag(j['emi']),
        payment: _flag(j['payment']),
        label: (j['label'] as String?) ?? (j['details'] as String),
      );
}

class CardEmi {
  const CardEmi({required this.name, required this.number, required this.tenure, required this.left,
      required this.principal, required this.interest, required this.gst, required this.amount});

  final String name;
  final int? number; // null for GST on fees
  final int? tenure;
  final int? left;
  final double principal;
  final double interest;
  final double gst;
  final double amount;

  String get label => number == null ? '' : tenure == null ? '$number' : '$number/$tenure';

  factory CardEmi.fromJson(Map<String, dynamic> j) => CardEmi(
        name: j['name'] as String,
        number: (j['number'] as num?)?.toInt(),
        tenure: (j['tenure'] as num?)?.toInt(),
        left: (j['left'] as num?)?.toInt(),
        principal: (j['principal'] as num).toDouble(),
        interest: (j['interest'] as num).toDouble(),
        gst: (j['gst'] as num? ?? 0).toDouble(),
        amount: (j['amount'] as num).toDouble(),
      );
}

/// One credit card statement. These stay apart from spending and budgets.
class CardStatement {
  const CardStatement({
    required this.card,
    required this.last4,
    required this.statementDate,
    required this.dueDate,
    required this.totalDue,
    required this.minDue,
    required this.creditLimit,
    required this.available,
    required this.balanced,
    required this.rows,
    required this.emis,
    required this.others,
  });

  final String card;
  final String last4;
  final String statementDate; // YYYY-MM-DD
  final String dueDate;
  final double totalDue;
  final double minDue;
  final double creditLimit;
  final double available;
  final bool balanced;
  final List<CardRow> rows;
  final List<CardEmi> emis;
  final double others; // total due less the EMIs and GST

  double get emiTotal => emis.fold(0.0, (a, e) => a + e.amount);
  String get month => statementDate.substring(0, 7);

  factory CardStatement.fromJson(Map<String, dynamic> j) => CardStatement(
        card: j['card'] as String,
        last4: (j['last4'] as String?) ?? '',
        statementDate: j['statement_date'] as String,
        dueDate: j['due_date'] as String,
        totalDue: (j['total_due'] as num).toDouble(),
        minDue: (j['min_due'] as num).toDouble(),
        creditLimit: (j['credit_limit'] as num).toDouble(),
        available: (j['available'] as num).toDouble(),
        balanced: _flag(j['balanced']),
        rows: _list(j['rows']).map((e) => CardRow.fromJson(e)).toList(),
        emis: _list(j['emis']).map((e) => CardEmi.fromJson(e)).toList(),
        others: (j['others'] as num? ?? 0).toDouble(),
      );
}

class Ledger {
  const Ledger({
    required this.transactions,
    required this.categories,
    required this.subcategories,
    required this.balances,
    required this.lastSync,
    required this.loans,
    required this.paid,
    required this.budgets,
    required this.budgetMonths,
    required this.budgetCategories,
    required this.mandatory,
    required this.publishedAt,
    required this.groceryMonths,
    required this.groceryProblems,
    required this.cardStatements,
    required this.cardProblems,
  });

  final List<Txn> transactions;
  final Map<String, String> categories; // name -> expense, savings, income...
  final Map<String, List<String>> subcategories;
  final List<Balance> balances;
  final DateTime? lastSync;
  final List<Loan> loans;
  final Set<String> paid; // "loanId|YYYY-MM" for each EMI ticked as paid
  final Map<String, double> budgets; // default monthly budget per spending category
  final Map<String, Map<String, double>> budgetMonths; // month -> category -> budget, replacing the default
  final Set<String> budgetCategories; // always listed on the budget page
  final Set<String> mandatory; // spending categories that must be paid
  final DateTime? publishedAt; // when the Mac sent this copy
  final Map<String, Map<String, dynamic>> groceryMonths; // month -> figures the Mac worked out
  final List<String> groceryProblems;
  final List<CardStatement> cardStatements; // newest first
  final List<String> cardProblems;

  double budgetFor(String category, String month) => budgetMonths[month]?[category] ?? budgets[category] ?? 0;

  bool isPaid(Loan loan, String month) => paid.contains('${loan.id}|$month');

  /// Throws FormatException or TypeError when the text is not a snapshot from the Mac.
  static Ledger parse(String body) {
    final j = _object(body);
    final lastSync = int.tryParse('${j['last_sync'] ?? ''}');
    final published = (j['published_ts'] as num?)?.toInt();
    final grocery = _object2(j['grocery'] ?? {});
    final cards = _object2(j['cards'] ?? {});
    return Ledger(
      transactions: _list(j['transactions']).map((e) => Txn.fromJson(e)).toList(),
      categories: {for (final e in _object2(j['categories']).entries) e.key: e.value as String},
      subcategories: {
        for (final e in _object2(j['subcategories']).entries)
          e.key: (e.value as List).map((n) => n as String).toList(),
      },
      balances: _list(j['balances']).map((e) => Balance.fromJson(e)).toList(),
      lastSync: lastSync == null ? null : DateTime.fromMillisecondsSinceEpoch(lastSync * 1000),
      loans: _list(j['loans']).map((e) => Loan.fromJson(e)).toList(),
      paid: {for (final p in _list(j['payments'])) '${p['loan_id']}|${p['month']}'},
      budgets: {for (final e in _object2(j['budgets'] ?? {}).entries) e.key: (e.value as num).toDouble()},
      budgetMonths: {
        for (final m in _object2(j['budget_months'] ?? {}).entries)
          m.key: {for (final e in _object2(m.value).entries) e.key: (e.value as num).toDouble()},
      },
      budgetCategories: {for (final c in (j['budget_categories'] as List? ?? const [])) c as String},
      mandatory: {for (final m in (j['mandatory'] as List? ?? const [])) m as String},
      groceryMonths: {
        for (final e in _object2(grocery['months'] ?? {}).entries) e.key: _object2(e.value),
      },
      groceryProblems: [for (final p in _list(grocery['problems'])) p['message'] as String],
      cardStatements: _list(cards['statements']).map((e) => CardStatement.fromJson(e)).toList(),
      cardProblems: [for (final p in _list(cards['problems'])) '${p['card']}: ${p['message']}'],
      publishedAt: published == null ? null : DateTime.fromMillisecondsSinceEpoch(published * 1000),
    );
  }
}

Map<String, dynamic> _object(String body) => Map<String, dynamic>.from(jsonDecode(body) as Map);
Map<String, dynamic> _object2(Object? value) => Map<String, dynamic>.from(value as Map);
List<Map<String, dynamic>> _list(Object? value) =>
    (value as List? ?? const []).map((e) => Map<String, dynamic>.from(e as Map)).toList();
