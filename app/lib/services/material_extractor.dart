import 'dart:io';

import 'package:archive/archive_io.dart';
import 'package:xml/xml.dart';

import '../models/app_picked_file.dart';
import '../models/material_info.dart';

class MaterialExtractor {
  Future<MaterialInfo> extract(AppPickedFile? file) async {
    if (file == null) {
      return const MaterialInfo(name: '', type: '', text: '', sections: []);
    }

    final extension = file.name.split('.').last.toLowerCase();
    if (extension == 'pptx') return _extractPptx(file);
    if (extension == 'pdf') {
      return MaterialInfo(
        name: file.name,
        type: 'PDF',
        text: '',
        sections: const [],
        error: '앱 내 PDF 텍스트 추출은 아직 지원하지 않습니다. PPTX 자료는 반영률 분석이 가능합니다.',
      );
    }

    return MaterialInfo(
      name: file.name,
      type: extension.toUpperCase(),
      text: '',
      sections: const [],
      error: '지원하지 않는 발표자료 형식입니다.',
    );
  }

  Future<MaterialInfo> _extractPptx(AppPickedFile file) async {
    try {
      final bytes = await File(file.path).readAsBytes();
      final archive = ZipDecoder().decodeBytes(bytes);
      final slideFiles =
          archive.files
              .where(
                (item) =>
                    item.isFile &&
                    RegExp(r'^ppt/slides/slide\d+\.xml$').hasMatch(item.name),
              )
              .toList()
            ..sort(
              (a, b) => _slideNumber(a.name).compareTo(_slideNumber(b.name)),
            );

      final sections = <MaterialSection>[];
      for (final slide in slideFiles) {
        final xml = XmlDocument.parse(String.fromCharCodes(slide.content));
        final texts = xml
            .findAllElements('a:t')
            .map((node) => node.innerText.trim())
            .where((text) => text.isNotEmpty)
            .toList();
        final page = _slideNumber(slide.name);
        final body = texts.join(' ').trim();
        sections.add(
          MaterialSection(
            page: page,
            title: texts.isEmpty ? 'Slide $page' : texts.first,
            text: body,
          ),
        );
      }

      final fullText = sections.map((item) => item.text).join('\n').trim();
      return MaterialInfo(
        name: file.name,
        type: 'PPTX',
        text: fullText,
        sections: sections,
        error: fullText.isEmpty ? 'PPTX에서 텍스트를 찾지 못했습니다.' : '',
      );
    } catch (error) {
      return MaterialInfo(
        name: file.name,
        type: 'PPTX',
        text: '',
        sections: const [],
        error: 'PPTX 텍스트 추출 실패: $error',
      );
    }
  }

  int _slideNumber(String path) {
    final match = RegExp(r'slide(\d+)\.xml$').firstMatch(path);
    return int.tryParse(match?.group(1) ?? '') ?? 0;
  }
}
