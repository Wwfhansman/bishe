import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../utils/constants.dart';

class ApiService {
  final Dio _dio = Dio(BaseOptions(
    baseUrl: ConstantConfigs.baseUrl,
    headers: {
      'ngrok-skip-browser-warning': 'true',  // Bypass ngrok free tier interstitial page
    },
  ));

  String _extractError(Object e) {
    if (e is DioException) {
      final code = e.response?.statusCode;
      final data = e.response?.data;
      final message = e.message ?? e.error?.toString() ?? e.toString();
      return 'DioException(code: $code, message: $message, data: $data)';
    }
    return e.toString();
  }

  Future<String?> getToken() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString('voice_token');
  }

  Future<void> setToken(String token) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('voice_token', token);
  }

  Future<void> clearToken() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('voice_token');
  }

  Future<void> clearUserId() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('voice_user_id');
  }

  Future<String?> getUserId() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString('voice_user_id');
  }

  Future<void> setUserId(String userId) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('voice_user_id', userId);
  }

  Future<Map<String, dynamic>> login(String username, String password) async {
    try {
      debugPrint('ApiService.login -> ${ConstantConfigs.baseUrl}/api/auth/login');
      final response = await _dio.post('/api/auth/login', data: {
        'username': username,
        'password': password,
      });
      if (response.data['ok'] == true) {
        await setToken(response.data['token']);
        await setUserId(response.data['user_id']);
      }
      return response.data;
    } catch (e) {
      final error = _extractError(e);
      debugPrint('ApiService.login error: $error');
      return {'ok': false, 'error': error};
    }
  }

  Future<Map<String, dynamic>> register(String username, String password) async {
    try {
      debugPrint('ApiService.register -> ${ConstantConfigs.baseUrl}/api/auth/register');
      final response = await _dio.post('/api/auth/register', data: {
        'username': username,
        'password': password,
      });
      if (response.data['ok'] == true) {
        await setToken(response.data['token']);
        await setUserId(response.data['user_id']);
      }
      return response.data;
    } catch (e) {
      final error = _extractError(e);
      debugPrint('ApiService.register error: $error');
      return {'ok': false, 'error': error};
    }
  }

  Future<List<dynamic>> getSessions() async {
    try {
      final token = await getToken();
      final userId = await getUserId();
      final options = token != null ? Options(headers: {'Authorization': 'Bearer $token'}) : null;
      final url = token != null ? '/api/sessions' : '/api/sessions?user_id=$userId';
      
      final response = await _dio.get(url, options: options);
      return response.data['sessions'] ?? [];
    } catch (e) {
      return [];
    }
  }

  Future<String?> createSession() async {
    try {
      final token = await getToken();
      final userId = await getUserId();
      
      final options = token != null ? Options(headers: {'Authorization': 'Bearer $token'}) : null;
      final data = token != null ? {} : {'user_id': userId};
      
      final response = await _dio.post('/api/sessions', data: data, options: options);
      return response.data['session_id'];
    } catch (e) {
      return null;
    }
  }
}
