import 'package:flutter/material.dart';

import 'data.dart';
import 'money.dart';
import 'settings.dart';
import 'theme.dart';

const figures = [FontFeature.tabularFigures()];
const pagePadding = EdgeInsets.fromLTRB(16, 4, 16, 24);

/// A white card on the page, with an optional heading.
class Panel extends StatefulWidget {
  const Panel({super.key, this.title, this.note, this.trailing, required this.child});
  final String? title;
  final String? note;
  final Widget? trailing;
  final Widget child;

  /// Titles of the panels the user has closed, kept across restarts.
  static Set<String> shut = {};

  @override
  State<Panel> createState() => _PanelState();
}

class _PanelState extends State<Panel> {
  void _toggle() {
    final title = widget.title!;
    setState(() => Panel.shut.contains(title) ? Panel.shut.remove(title) : Panel.shut.add(title));
    AppSettings.saveShutPanels(Panel.shut);
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final title = widget.title;
    final closed = title != null && Panel.shut.contains(title);
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
      decoration: BoxDecoration(
        color: scheme.surface,
        border: Border.all(color: context.palette.line),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (title != null)
            Semantics(
              button: true,
              label: closed ? 'Open $title' : 'Close $title',
              child: InkWell(
                onTap: _toggle,
                child: Row(
                  children: [
                    Expanded(child: Text(title, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600))),
                    ?widget.trailing,
                    Icon(closed ? Icons.expand_more : Icons.expand_less, size: 20, color: scheme.onSurfaceVariant),
                  ],
                ),
              ),
            ),
          if (!closed) ...[
            if (widget.note != null)
              Padding(
                padding: const EdgeInsets.only(top: 2),
                child: Text(widget.note!, style: TextStyle(fontSize: 12.5, color: scheme.onSurfaceVariant)),
              ),
            if (title != null || widget.note != null) const SizedBox(height: 10),
            widget.child,
          ],
        ],
      ),
    );
  }
}

/// The one number a screen is about.
class Headline extends StatelessWidget {
  const Headline({super.key, required this.label, required this.value, this.detail, this.color});
  final String label;
  final String value;
  final String? detail;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: TextStyle(fontSize: 13, color: muted)),
        const SizedBox(height: 2),
        FittedBox(
          fit: BoxFit.scaleDown,
          alignment: Alignment.centerLeft,
          child: Text(
            value,
            style: TextStyle(
              fontSize: 34, fontWeight: FontWeight.w700, letterSpacing: -0.6, height: 1.15, color: color,
              fontFeatures: figures,
            ),
          ),
        ),
        if (detail != null)
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Text(detail!, style: TextStyle(fontSize: 13, color: muted)),
          ),
      ],
    );
  }
}

/// A small labelled figure, for rows under a headline.
class Stat extends StatelessWidget {
  const Stat({super.key, required this.label, required this.value, this.detail, this.color});
  final String label;
  final String value;
  final String? detail;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 12, color: muted)),
        const SizedBox(height: 1),
        Text(
          value,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: color, fontFeatures: figures),
        ),
        if (detail != null)
          Text(detail!, maxLines: 2, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 11.5, color: muted)),
      ],
    );
  }
}

/// A thin bar showing how much of something is used.
class Meter extends StatelessWidget {
  const Meter({super.key, required this.value, this.color, this.height = 6});
  final double value;
  final Color? color;
  final double height;

  @override
  Widget build(BuildContext context) {
    final fraction = value.isFinite ? value.clamp(0.0, 1.0) : 0.0;
    return ClipRRect(
      borderRadius: BorderRadius.circular(height / 2),
      child: Container(
        height: height,
        color: context.palette.track,
        alignment: Alignment.centerLeft,
        child: FractionallySizedBox(
          widthFactor: fraction,
          child: Container(
            decoration: BoxDecoration(
              color: color ?? context.palette.series,
              borderRadius: BorderRadius.circular(height / 2),
            ),
          ),
        ),
      ),
    );
  }
}

class Tag extends StatelessWidget {
  const Tag(this.text, {super.key});
  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
      decoration: BoxDecoration(
        border: Border.all(color: context.palette.line),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(text, style: TextStyle(fontSize: 10.5, color: Theme.of(context).colorScheme.onSurfaceVariant)),
    );
  }
}

/// One payment: a letter badge, who, what, and how much.
class TxnRow extends StatelessWidget {
  const TxnRow(this.t, {super.key, this.showDate = false});
  final Txn t;
  final bool showDate;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final p = context.palette;
    final tag = txnTag(t);
    final letter = t.payee.trim().isEmpty ? '?' : t.payee.trim()[0].toUpperCase();
    final sub = (t.subcategory ?? '').isEmpty ? null : t.subcategory;
    final meta = [if (showDate) dayLabel(t.date), t.category, ?sub, t.account, ?t.note].join(' · ');
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 34,
            height: 34,
            alignment: Alignment.center,
            decoration: BoxDecoration(color: p.track, shape: BoxShape.circle),
            child: Text(letter, style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: scheme.onSurfaceVariant)),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Flexible(
                      child: Text(t.payee, maxLines: 1, overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w500)),
                    ),
                    if (t.approved) ...[
                      const SizedBox(width: 4),
                      Icon(Icons.check_circle, size: 13, color: p.good, semanticLabel: 'Approved'),
                    ],
                  ],
                ),
                Text(meta, maxLines: 2, overflow: TextOverflow.ellipsis,
                    style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant)),
                if (tag != null) Padding(padding: const EdgeInsets.only(top: 3), child: Tag(tag)),
              ],
            ),
          ),
          const SizedBox(width: 10),
          Text(
            '${t.credit ? '+' : ''}${inr(t.amount)}',
            style: TextStyle(
              fontSize: 14, fontWeight: FontWeight.w600, fontFeatures: figures,
              color: t.credit ? p.good : null,
            ),
          ),
        ],
      ),
    );
  }
}

/// A list that starts short, with a button for the rest.
class ShowMore extends StatefulWidget {
  const ShowMore({super.key, required this.children, this.first = 4});
  final List<Widget> children;
  final int first;

  @override
  State<ShowMore> createState() => _ShowMoreState();
}

class _ShowMoreState extends State<ShowMore> {
  bool _all = false;

  @override
  Widget build(BuildContext context) {
    final extra = widget.children.length - widget.first;
    final shown = _all || extra <= 0 ? widget.children : widget.children.take(widget.first).toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ...shown,
        if (extra > 0)
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton(
              style: TextButton.styleFrom(padding: EdgeInsets.zero, minimumSize: const Size(0, 36)),
              onPressed: () => setState(() => _all = !_all),
              child: Text(_all ? 'Show less' : 'Show $extra more'),
            ),
          ),
      ],
    );
  }
}
