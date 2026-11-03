import 'dart:convert';

import 'package:expense_tracker/home_page.dart';
import 'package:expense_tracker/theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'sample_snapshot.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({'snapshot_json': jsonEncode(sampleSnapshot)});
    FlutterSecureStorage.setMockInitialValues({});
  });

  Future<void> pumpPhone(WidgetTester tester, {double width = 360, ThemeData? theme}) async {
    await tester.binding.setSurfaceSize(Size(width, 800));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(MaterialApp(theme: theme ?? lightTheme, home: const HomePage()));
    await tester.pumpAndSettle();
  }

  for (final (name, theme) in [('light', lightTheme), ('dark', darkTheme)]) {
    testWidgets('every tab lays out on a narrow phone, $name', (tester) async {
      await pumpPhone(tester, width: 320, theme: theme);
      expect(tester.takeException(), isNull);
      expect(find.text('Spent'), findsOneWidget);
      expect(find.text('Add expense'), findsNothing);
      await tester.tap(find.text('Budget').last);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(find.text('Total of all'), findsOneWidget);
      await tester.tap(find.text('Grocery').last);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(find.text('Detailed by bills'), findsOneWidget);
      expect(find.textContaining('₹140 → ₹99'), findsNothing); // below the first screen until scrolled
      await tester.tap(find.text('Cards').last);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      await tester.tap(find.text('Loans').last);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(find.text('Left to pay'), findsOneWidget);
    });
  }

  testWidgets('a category opens its transactions', (tester) async {
    await pumpPhone(tester);
    await tester.scrollUntilVisible(find.text('Spending by category'), 200, scrollable: find.byType(Scrollable).first);
    await tester.drag(find.byType(Scrollable).first, const Offset(0, -200));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Groceries').first);
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(find.textContaining('Groceries ·'), findsWidgets);
  });

  testWidgets('with nothing saved it offers to sync', (tester) async {
    SharedPreferences.setMockInitialValues({});
    await pumpPhone(tester);
    expect(find.text('Sync now'), findsOneWidget);
  });
}
