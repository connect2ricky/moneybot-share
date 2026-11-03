import 'dart:convert';
import 'dart:typed_data';

import 'package:expense_tracker/data.dart';
import 'package:expense_tracker/money.dart';
import 'package:expense_tracker/sync.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'sample_snapshot.dart';

Ledger _ledger() => Ledger.parse(jsonEncode(sampleSnapshot));

void main() {
  group('formatting', () {
    test('rupees use Indian grouping', () {
      expect(inr(0), '₹0');
      expect(inr(999), '₹999');
      expect(inr(1903), '₹1,903');
      expect(inr(1234567), '₹12,34,567');
      expect(inr(10023785), '₹1,00,23,785');
      expect(inr(-250), '−₹250');
    });

    test('short labels for charts', () {
      expect(shortInr(850), '₹850');
      expect(shortInr(5400), '₹5k');
      expect(shortInr(150000), '₹1.5L');
      expect(shortInr(2000000), '₹20L');
    });

    test('months and days read like the dashboard', () {
      expect(monthName('2026-10'), 'Oct 2026');
      expect(dayLabel('2026-10-05'), '05 Oct');
      expect(shiftMonth('2026-01', -1), '2025-12');
      expect(shiftMonth('2026-10', -12), '2025-10');
      expect(deltaText(120, 100, 'Sep 2026'), '▲ 20% vs Sep 2026 (₹100)');
      expect(deltaText(50, 0, 'Sep 2026'), 'no data for Sep 2026');
    });

    test('months with no transactions are filled in', () {
      final months = monthsWithGaps(_ledger().transactions);
      expect(months, ['2026-09', '2026-10']);
    });
  });

  group('spending totals', () {
    test('pending and approved expenses count, received money and transfers do not', () {
      final led = _ledger();
      final oct = totalsFor(led, '2026-10', '');
      expect(oct.spend, 1500); // 1200 approved + 300 pending
      expect(oct.pending, 300);
      expect(oct.categories['Groceries'], 1200);
      expect(oct.categories['Pending review'], 300);
      expect(oct.subs['Groceries']!['Vegetables'], 1200);
      expect(oct.saved, 0);
    });

    test('an account filter narrows the totals', () {
      final led = _ledger();
      expect(totalsFor(led, '2026-09', 'HDFC 2').spend, 800);
      expect(totalsFor(led, '2026-09', 'Axis 1').spend, 0); // the card bill is not counted
    });

    test('savings are counted separately from spending', () {
      final led = Ledger.parse(jsonEncode({
        ...sampleSnapshot,
        'transactions': [
          {'key': 'f', 'date': '2026-10-02', 'account': 'Axis 1', 'direction': 'debit', 'amount': 2000.0,
            'payee': 'Fund', 'channel': 'UPI', 'app': null, 'category': 'Savings', 'subcategory': null,
            'status': 'approved', 'counted': 1, 'note': null},
        ],
      }));
      final oct = totalsFor(led, '2026-10', '');
      expect(oct.saved, 2000);
      expect(oct.spend, 0);
    });
  });

  group('loans', () {
    test('months left, paid this month, and preclose estimate', () {
      final led = _ledger();
      const now = '2026-10';
      final monitor = led.loans.first;
      // Oct to Dec is three EMIs; October is ticked as paid, so two are left.
      expect(loanLeft(monitor, led, now), 2);
      expect(monthCount('2026-10', '2026-12'), 3);
      expect(loanPreclose(monitor, led, now)! > 0, isTrue);
      expect(loanPreclose(led.loans[1], led, now), isNull);
    });

    test('EMI in a month', () {
      final led = _ledger();
      expect(emiIn(led, '2026-10'), 5624 + 3000);
      expect(emiIn(led, '2026-12'), 5624);
    });
  });

  group('snapshot', () {
    test('parses balances, loans, payments and the sync time', () {
      final led = _ledger();
      expect(led.balances.first.balance, 1000.5);
      expect(led.balances.first.fromAlert, isTrue);
      expect(led.balances.last.balance, isNull);
      expect(led.isPaid(led.loans.first, '2026-10'), isTrue);
      expect(led.lastSync, DateTime.fromMillisecondsSinceEpoch(1792570883 * 1000));
    });

    test('a bad body is rejected rather than shown', () {
      expect(() => Ledger.parse('{"transactions": "nope"}'), throwsA(anything));
    });
  });

  group('sync client', () {
    const key = 'AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=';
    final file = base64.decode(
        'TUJQMU1dKKLlQ7BE1tpnmmO7D32epIdGCQDI+Jy/a3TMCL7RwevCMCybX1JViwIv7VAPukisyUn/ZxCAgGyJcvp8wVki/M8RNOg=');

    SyncClient clientReturning(http.Response Function(http.Request) handler, {String k = key}) =>
        SyncClient(SyncSettings(token: 'secret', key: k), client: MockClient((request) async => handler(request)),
            url: 'https://api.github.com/repos/someone/moneybot-data/contents/moneybot.mbp?ref=phone');

    test('opens a file the Mac encrypted, with the token sent to GitHub', () async {
      late http.Request seen;
      final client = clientReturning((request) {
        seen = request;
        return http.Response.bytes(file, 200);
      });
      expect(await client.fetchSnapshot(), '{"hello": "₹ world"}');
      expect(seen.url.host, 'api.github.com');
      expect(seen.url.queryParameters['ref'], 'phone');
      expect(seen.headers['Authorization'], 'Bearer secret');
    });

    test('a wrong key says so', () {
      final wrong = base64Url.encode(List.filled(32, 7));
      final client = clientReturning((_) => http.Response.bytes(file, 200), k: wrong);
      expect(client.fetchSnapshot(), throwsA(isA<SyncException>().having((e) => e.message, 'message', contains('phone key'))));
    });

    test('a damaged file is refused', () {
      final bad = Uint8List.fromList(file)..[20] ^= 1;
      final client = clientReturning((_) => http.Response.bytes(bad, 200));
      expect(client.fetchSnapshot(), throwsA(isA<SyncException>()));
    });

    test('a key that is not a key says so', () {
      final client = clientReturning((_) => http.Response.bytes(file, 200), k: 'short');
      expect(client.fetchSnapshot(), throwsA(isA<SyncException>().having((e) => e.message, 'message', contains('not valid'))));
    });

    test('an expired token says so', () {
      final client = clientReturning((_) => http.Response('{}', 401));
      expect(client.fetchSnapshot(), throwsA(isA<SyncException>().having((e) => e.message, 'message', contains('token'))));
    });

    test('no network says so', () {
      final client = clientReturning((_) => throw http.ClientException('no route'));
      expect(client.fetchSnapshot(), throwsA(isA<SyncException>().having((e) => e.message, 'message', contains('internet'))));
    });

    test('settings need both values', () {
      expect(const SyncSettings(token: '', key: 'k').isSet, isFalse);
      expect(const SyncSettings(token: 't', key: 'k').isSet, isTrue);
    });
  });

  test('daily bars add up to the month and fit its length', () {
    final led = _ledger();
    final days = dailySpend(led, '2026-10', '');
    expect(days.length, 31);
    expect(dailySpend(led, '2026-09', '').length, 30);
    expect(days.fold(0.0, (a, v) => a + v), totalsFor(led, '2026-10', '').spend);
    expect(days[4], greaterThan(0)); // the 5th
    final onThe5th = spendingIn(led, '2026-10', '').where((t) => t.date == '2026-10-05');
    expect(onThe5th.fold(0.0, (a, t) => a + t.amount), days[4]);
  });

  test('daily bars can leave out loans', () {
    final led = Ledger.parse(jsonEncode({
      ...sampleSnapshot,
      'transactions': [
        ...sampleSnapshot['transactions'] as List,
        {'key': 'l', 'date': '2026-10-05', 'account': 'Axis 1', 'direction': 'debit', 'amount': 700.0,
          'payee': 'Bank', 'channel': 'NACH', 'app': null, 'category': 'Loan EMI', 'subcategory': null,
          'status': 'approved', 'counted': 1, 'note': null},
      ],
    }));
    final all = dailySpend(led, '2026-10', '')[4];
    expect(dailySpend(led, '2026-10', '', noLoans: true)[4], all - 700);
  });

  group('at this time last month', () {
    test('counts only the same days of last month', () {
      final led = _ledger();
      final spent = totalsFor(led, '2026-10', '').spend;
      final then = totalsFor(led, '2026-09', '', upToDay: 11).spend;
      expect(then, 800);
      expect(totalsFor(led, '2026-09', '', upToDay: 1).spend, 0);
      final pace = soFar(led, '2026-10', '', spent, DateTime(2026, 10, 11))!;
      expect(pace.text, contains(inr(then)));
      expect(pace.up, spent > then);
      expect(soFar(led, '2026-10', '', 100, DateTime(2026, 10, 11))!.down, isTrue);
    });

    test('amount left is salary less spending, with all accounts in view', () {
      final led = Ledger.parse(jsonEncode({
        ...sampleSnapshot,
        'transactions': [
          ...sampleSnapshot['transactions'] as List,
          {'key': 's', 'date': '2026-10-01', 'account': 'Axis 1', 'direction': 'credit', 'amount': 5000.0,
            'payee': 'Employer', 'channel': 'NEFT', 'app': null, 'category': 'Salary', 'subcategory': null,
            'status': 'auto', 'counted': 1, 'note': null},
        ],
      }));
      expect(leftLine(led, '2026-10', '', 1500), 'Left from salary ${inr(3500)}');
      expect(leftLine(led, '2026-09', '', 1500), 'No salary this month yet');
      expect(leftLine(led, '2026-10', 'Axis 1', 1500), isNull);
    });

    test('is not shown for a month already over', () {
      expect(soFar(_ledger(), '2026-09', '', 100, DateTime(2026, 10, 11)), isNull);
    });
  });

  group('budget', () {
    test('budgets come from the snapshot', () {
      final led = _ledger();
      expect(led.budgets, {'Groceries': 2000.0, 'Food & Dining': 500.0});
    });

    test('spent matches the spending page and pending payments are left out', () {
      final led = _ledger();
      final rows = budgetRows(led, '2026-10');
      final groceries = rows.firstWhere((r) => r.name == 'Groceries');
      expect(groceries.spent, 1200);
      expect(groceries.left, 800);
      expect(groceries.over, isFalse);
      final food = rows.firstWhere((r) => r.name == 'Food & Dining');
      expect(food.spent, 0); // its 300 is still pending review
      expect(food.left, 500);
    });

    test('a month replaces the default, and zero means no budget', () {
      final led = Ledger.parse(jsonEncode({
        ...sampleSnapshot,
        'budget_months': {
          '2026-09': {'Groceries': 900.0},
          '2026-08': {'Groceries': 0},
        },
      }));
      expect(led.budgetFor('Groceries', '2026-09'), 900);
      expect(led.budgetFor('Groceries', '2026-08'), 0);
      expect(led.budgetFor('Groceries', '2026-10'), 2000);
      expect(budgetRows(led, '2026-10').firstWhere((r) => r.name == 'Groceries').budget, 2000);
    });

    test('a default budget stays listed when a month sets it to zero', () {
      final led = Ledger.parse(jsonEncode({
        ...sampleSnapshot,
        'budget_months': {'2099-01': {'Groceries': 0.0}},
      }));
      final row = budgetRows(led, '2099-01').firstWhere((r) => r.name == 'Groceries');
      expect(row.hasBudget, isFalse);
    });

    test('a budget for one month only is listed in that month', () {
      final led = Ledger.parse(jsonEncode({
        ...sampleSnapshot,
        'budgets': <String, double>{},
        'budget_months': {'2026-01': {'Groceries': 700.0}},
      }));
      expect(budgetRows(led, '2026-01').firstWhere((r) => r.name == 'Groceries').budget, 700);
    });

    test('a month to come lists its budgets though nothing is spent yet', () {
      final rows = budgetRows(_ledger(), '2099-01');
      expect(rows.map((r) => r.name), containsAll(['Groceries', 'Food & Dining']));
      expect(rows.every((r) => r.spent == 0), isTrue);
    });

    test('budgeted categories come first, and an overspend is flagged', () {
      final led = Ledger.parse(jsonEncode({
        ...sampleSnapshot,
        'budgets': {'Groceries': 1000.0},
      }));
      final rows = budgetRows(led, '2026-10');
      expect(rows.first.name, 'Groceries');
      expect(rows.first.over, isTrue); // 1200 spent against 1000
      expect(rows.first.left, -200);
    });
  });
}
