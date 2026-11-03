/// A small snapshot in the same shape the Mac sends.
const sampleSnapshot = {
  'transactions': [
    {'key': 'a', 'date': '2026-10-05', 'account': 'Axis 1', 'direction': 'debit', 'amount': 1200.0,
      'payee': 'Big Bazaar', 'channel': 'UPI', 'app': null, 'category': 'Groceries', 'subcategory': 'Vegetables',
      'status': 'approved', 'counted': 1, 'note': null},
    {'key': 'b', 'date': '2026-10-09', 'account': 'Axis 1', 'direction': 'debit', 'amount': 300.0,
      'payee': 'Swiggy', 'channel': 'Card', 'app': null, 'category': 'Food & Dining', 'subcategory': null,
      'status': 'pending', 'counted': 1, 'note': 'dinner'},
    {'key': 'c', 'date': '2026-10-10', 'account': 'Axis 1', 'direction': 'credit', 'amount': 5000.0,
      'payee': 'Salary', 'channel': 'NEFT', 'app': null, 'category': 'Income', 'subcategory': null,
      'status': 'approved', 'counted': 1, 'note': null},
    {'key': 'd', 'date': '2026-09-02', 'account': 'HDFC 2', 'direction': 'debit', 'amount': 800.0,
      'payee': 'Netflix', 'channel': 'Card', 'app': null, 'category': 'Digital & Subscriptions', 'subcategory': 'Netflix',
      'status': 'approved', 'counted': 1, 'note': null},
    {'key': 'e', 'date': '2026-09-12', 'account': 'Axis 1', 'direction': 'debit', 'amount': 1000.0,
      'payee': 'Card bill', 'channel': 'Transfer', 'app': null, 'category': 'Savings', 'subcategory': null,
      'status': 'approved', 'counted': 0, 'note': null},
  ],
  'categories': {
    'Groceries': 'expense', 'Food & Dining': 'expense', 'Digital & Subscriptions': 'expense',
    'Savings': 'savings', 'Income': 'income',
  },
  'subcategories': {'Groceries': ['Vegetables'], 'Digital & Subscriptions': ['Netflix']},
  'balances': [
    {'account': 'Axis 1', 'balance': 1000.5, 'confirmed': 2000.0, 'confirmed_ts': 1792575088, 'source': 'alert',
      'since': 0, 'in_total': true},
    {'account': 'HDFC 2', 'balance': null, 'confirmed': null, 'confirmed_ts': null, 'source': null,
      'since': null, 'in_total': false},
  ],
  'last_sync': '1792570883',
  'loans': [
    {'id': 1, 'lender': 'HDFC CC', 'name': 'Monitor', 'principal': 89470.0, 'rate': 16.0, 'emi': 5624.0,
      'first_month': '2026-09', 'last_month': '2026-12', 'note': null, 'separate': 0},
    {'id': 2, 'lender': 'Other', 'name': 'Bike', 'principal': null, 'rate': null, 'emi': 3000.0,
      'first_month': '2026-01', 'last_month': '2026-10', 'note': 'closes soon', 'separate': 1},
  ],
  'payments': [{'loan_id': 1, 'month': '2026-10'}],
  'grocery': {
    'problems': [
      {'message': 'No matching payment for the Star Bazaar bill of ₹77.00 on 09 Oct', 'url': null},
    ],
    'months': {
      '2026-09': {'total': 500.0, 'billed': 0.0, 'subcategories': [], 'groups': [], 'items': [], 'bills': []},
      '2026-10': {
        'total': 1200.0,
        'billed': 219.5,
        'subcategories': [
          {'name': 'Star/Ratnadeep/Ushodaya', 'amount': 700.0, 'payees': ['STAR BAZAAR']},
          {'name': 'Milk', 'amount': 500.0, 'payees': ['SURESH DAIRY']},
        ],
        'groups': [
          {'name': 'Fruit', 'amount': 200.5},
        ],
        'items': [
          {
            'code': '1', 'name': 'Guava Jmb Pnk', 'unit': 'KG', 'group': 'Fruit', 'quantity': 2.05, 'amount': 200.5,
            'price': 99.0,
            'history': [
              {'date': '2026-10-08', 'price': 140.0},
              {'date': '2026-10-23', 'price': 99.0},
            ],
          },
        ],
        'bills': [
          {
            'id': 'star:1', 'source': 'Star Bazaar', 'date': '2026-10-23', 'total': 219.5, 'matched': true,
            'items': [
              {'name': 'Guava Jmb Pnk', 'quantity': 2.05, 'unit': 'KG', 'price': 99.0, 'amount': 200.5},
              {'name': 'Carry Bag18*24', 'quantity': 1.0, 'unit': 'PC', 'price': 19.0, 'amount': 19.0},
            ],
          },
        ],
      },
    },
  },
  'budgets': {'Groceries': 2000.0, 'Food & Dining': 500.0},
  'budget_categories': ['Gifts'],
  'cards': {
    'statements': [
      {
        'card': 'Axis Rewards', 'last4': '1111', 'period_start': '2026-09-23', 'period_end': '2026-10-21',
        'statement_date': '2026-10-21', 'due_date': '2026-11-10', 'total_due': 6206.88, 'min_due': 500.0,
        'previous': 6215.39, 'credit_limit': 241000.0, 'available': 234793.12, 'balanced': true,
        'rows': [
          {'date': '2026-09-27', 'details': 'A very long merchant name that has to wrap on a narrow phone screen', 'amount': 6206.88, 'credit': false, 'emi': true},
          {'date': '2026-10-01', 'details': 'BBPS PAYMENT RECEIVED', 'amount': 6215.39, 'credit': true, 'emi': false, 'payment': true},
          {'date': '2026-10-02', 'details': 'A long shop name that also has to wrap on a very narrow phone screen', 'amount': 100.0, 'credit': false, 'emi': false, 'payment': false},
        ],
        'emis': [
          {'name': 'A very long plan name that has to wrap on a narrow phone screen', 'number': 15, 'tenure': 48, 'left': 33,
           'principal': 3831.01, 'interest': 2013.45, 'gst': 362.42, 'amount': 6206.88},
          {'name': 'GST on fees', 'number': null, 'tenure': null, 'left': null,
           'principal': 0.0, 'interest': 0.0, 'gst': 7.56, 'amount': 7.56},
        ],
        'others': 0.0,
      },
    ],
    'problems': [{'card': 'Axis Neo', 'message': 'password not saved in the Keychain', 'count': 1}],
  },
};
