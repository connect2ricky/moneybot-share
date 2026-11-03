import 'dart:convert';
import 'dart:io' show gzip;
import 'dart:typed_data';

import 'package:cryptography/cryptography.dart';
import 'package:http/http.dart' as http;

/// Where the Mac publishes the encrypted data. install_personal.sh sets it from BACKUP_REPO in moneybot/config.py.
const _snapshotUrl = String.fromEnvironment('SNAPSHOT_URL');
final _magic = ascii.encode('MBP1');
const _nonceLength = 12;
const _macLength = 16;

class SyncException implements Exception {
  SyncException(this.message);
  final String message;
  @override
  String toString() => message;
}

class SyncSettings {
  const SyncSettings({required this.token, required this.key});
  final String token; // GitHub token that can only read the data repository
  final String key; // opens the encrypted file; the Mac prints it with `moneybot phone-key`

  bool get isSet => token.isNotEmpty && key.isNotEmpty;
}

/// Reads the dashboard's data from GitHub. Nothing is sent back: the phone only reads.
class SyncClient {
  SyncClient(this.settings, {http.Client? client, this.url = _snapshotUrl}) : _client = client ?? http.Client();

  final SyncSettings settings;
  final String url;
  final http.Client _client;
  static const _timeout = Duration(seconds: 30);

  /// The whole dashboard as JSON text.
  Future<String> fetchSnapshot() async {
    if (url.isEmpty) {
      throw SyncException('This build does not know where your data is. Install it with install_personal.sh.');
    }
    final http.Response response;
    try {
      response = await _client.get(Uri.parse(url), headers: {
        'Authorization': 'Bearer ${settings.token}',
        'Accept': 'application/vnd.github.raw+json',
        'X-GitHub-Api-Version': '2022-11-28',
      }).timeout(_timeout);
    } catch (_) {
      throw SyncException('Cannot reach GitHub. Check your internet connection.');
    }
    if (response.statusCode == 401) {
      throw SyncException('GitHub refused the token. It may have expired; add a new one in Settings.');
    }
    if (response.statusCode == 403 || response.statusCode == 404) {
      throw SyncException('This token cannot read the data, or the Mac has not published it yet.');
    }
    if (response.statusCode != 200) throw SyncException('GitHub answered with an error. Try again shortly.');
    return decryptSnapshot(response.bodyBytes, settings.key);
  }
}

/// Opens a file written by moneybot/phone.py: "MBP1" + nonce + AES-256-GCM(gzip(JSON)) + tag.
Future<String> decryptSnapshot(Uint8List blob, String key) async {
  final headLength = _magic.length + _nonceLength;
  if (blob.length < headLength + _macLength || !_startsWithMagic(blob)) {
    throw SyncException('The file from GitHub is not moneybot data.');
  }
  final List<int> keyBytes;
  try {
    keyBytes = base64Url.decode(base64Url.normalize(key.trim()));
  } on FormatException {
    throw SyncException('That phone key is not valid. Copy it again from the Mac.');
  }
  if (keyBytes.length != 32) throw SyncException('That phone key is not valid. Copy it again from the Mac.');
  try {
    final plain = await AesGcm.with256bits().decrypt(
      SecretBox(
        blob.sublist(headLength, blob.length - _macLength),
        nonce: blob.sublist(_magic.length, headLength),
        mac: Mac(blob.sublist(blob.length - _macLength)),
      ),
      secretKey: SecretKey(keyBytes),
      aad: _magic,
    );
    return utf8.decode(gzip.decode(plain));
  } on SecretBoxAuthenticationError {
    throw SyncException('The phone key does not open this data. Copy it again from the Mac.');
  }
}

bool _startsWithMagic(Uint8List blob) {
  for (var i = 0; i < _magic.length; i++) {
    if (blob[i] != _magic[i]) return false;
  }
  return true;
}
