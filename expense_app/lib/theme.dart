import 'package:flutter/material.dart';

/// The dashboard's palette: neutral surfaces, one blue for data, and good/serious kept for status.
class Palette extends ThemeExtension<Palette> {
  const Palette({
    required this.line,
    required this.track,
    required this.faint,
    required this.series,
    required this.seriesSoft,
    required this.compare,
    required this.good,
    required this.serious,
  });

  final Color line;
  final Color track;
  final Color faint;
  final Color series;
  final Color seriesSoft;
  final Color compare;
  final Color good;
  final Color serious;

  static const light = Palette(
    line: Color(0xFFE3E2DD), track: Color(0xFFECEBE6), faint: Color(0xFF85847E), series: Color(0xFF2A78D6),
    seriesSoft: Color(0xFFA9C8EE), compare: Color(0xFFB9B8B1), good: Color(0xFF1A7F37), serious: Color(0xFFC4380F),
  );
  static const dark = Palette(
    line: Color(0xFF32322F), track: Color(0xFF262624), faint: Color(0xFF8D8C84), series: Color(0xFF3987E5),
    seriesSoft: Color(0xFF25476F), compare: Color(0xFF5F5E58), good: Color(0xFF4CC26B), serious: Color(0xFFF0805A),
  );

  @override
  Palette copyWith() => this;

  @override
  Palette lerp(ThemeExtension<Palette>? other, double t) => t < 0.5 || other is! Palette ? this : other;
}

extension PaletteOf on BuildContext {
  Palette get palette => Theme.of(this).extension<Palette>()!;
}

ThemeData _theme(Brightness brightness, Palette p, Color page, Color surface, Color text, Color text2) {
  final scheme = ColorScheme.fromSeed(seedColor: p.series, brightness: brightness).copyWith(
    primary: p.series,
    onPrimary: Colors.white,
    surface: surface,
    onSurface: text,
    onSurfaceVariant: text2,
    surfaceContainerHighest: p.track,
    outline: p.compare,
    outlineVariant: p.line,
    error: p.serious,
  );
  return ThemeData(
    colorScheme: scheme,
    useMaterial3: true,
    scaffoldBackgroundColor: page,
    extensions: [p],
    dividerTheme: DividerThemeData(color: p.line, thickness: 1, space: 1),
    appBarTheme: AppBarTheme(
      backgroundColor: page,
      surfaceTintColor: Colors.transparent,
      scrolledUnderElevation: 0,
      titleSpacing: 16,
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: surface,
      surfaceTintColor: Colors.transparent,
      indicatorColor: p.seriesSoft.withValues(alpha: 0.45),
      height: 64,
      labelTextStyle: WidgetStatePropertyAll(TextStyle(fontSize: 12, fontWeight: FontWeight.w500, color: text2)),
    ),
    snackBarTheme: const SnackBarThemeData(behavior: SnackBarBehavior.floating),
    inputDecorationTheme: InputDecorationTheme(
      isDense: true,
      filled: true,
      fillColor: page,
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide(color: p.line)),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide(color: p.line)),
    ),
  );
}

final lightTheme = _theme(Brightness.light, Palette.light, const Color(0xFFF4F4F2), const Color(0xFFFCFCFB),
    const Color(0xFF0B0B0B), const Color(0xFF52514E));
final darkTheme = _theme(Brightness.dark, Palette.dark, const Color(0xFF111110), const Color(0xFF1A1A19),
    Colors.white, const Color(0xFFC3C2B7));
