import 'package:pdf/widgets.dart' as pw;

import '../models/analysis_result.dart';

class ReportBuilder {
  Future<List<int>> build(AnalysisResult analysis) async {
    final doc = pw.Document();
    doc.addPage(
      pw.MultiPage(
        build: (_) => [
          pw.Text('STT Presentation Review', style: pw.TextStyle(fontSize: 22)),
          pw.SizedBox(height: 12),
          pw.Text('Score: ${analysis.score} / Grade: ${analysis.grade}'),
          pw.Text('WPM: ${analysis.wpm} / Fillers: ${analysis.fillerTotal}'),
          pw.Text('Source: ${analysis.source}'),
          pw.SizedBox(height: 12),
          pw.Text('Summary', style: pw.TextStyle(fontSize: 16)),
          pw.Text(analysis.summary),
          pw.SizedBox(height: 12),
          pw.Text('Document Match', style: pw.TextStyle(fontSize: 16)),
          if (analysis.documentMatch.available) ...[
            pw.Text(
              'Score: ${analysis.documentMatch.score} / Coverage: ${analysis.documentMatch.documentCoverage}%',
            ),
            pw.Text(analysis.documentMatch.summary),
            if (analysis.documentMatch.missingTerms.isNotEmpty)
              pw.Text(
                'Missing terms: ${analysis.documentMatch.missingTerms.join(', ')}',
              ),
            for (final section in analysis.documentMatch.sections.take(12))
              pw.Bullet(
                text:
                    'Slide ${section.page}: ${section.score}% / ${section.status}',
              ),
          ] else
            pw.Text(analysis.documentMatch.summary),
          pw.SizedBox(height: 12),
          pw.Text('Priorities', style: pw.TextStyle(fontSize: 16)),
          for (final item in analysis.priorities) pw.Bullet(text: item),
          pw.SizedBox(height: 12),
          pw.Text('Problems', style: pw.TextStyle(fontSize: 16)),
          for (final item in analysis.problems) pw.Bullet(text: item),
          pw.SizedBox(height: 12),
          pw.Text('Transcript', style: pw.TextStyle(fontSize: 16)),
          pw.Text(analysis.transcript),
        ],
      ),
    );
    return doc.save();
  }
}
