import 'package:flutter/material.dart';

/// 妮妮厨房助理 — 全局暖色调设计系统
class AppColors {
  AppColors._();

  // 主色：深青绿 + 柔和薄荷
  static const Color primary = Color(0xFF1F6F78);
  static const Color primaryLight = Color(0xFF4FB3B0);
  static const Color primarySurface = Color(0xFFE7F6F4);

  // 背景：清爽浅灰与微暖白
  static const Color background = Color(0xFFF5F6F8);
  static const Color surface = Color(0xFFFFFFFF);
  static const Color surfaceVariant = Color(0xFFF1F5F9);

  // 文字：石墨黑层次
  static const Color textPrimary = Color(0xFF1C1F24);
  static const Color textSecondary = Color(0xFF4B5563);
  static const Color textHint = Color(0xFF94A3B8);

  // 辅助
  static const Color divider = Color(0xFFE5E7EB);
  static const Color error = Color(0xFFE5484D);
  static const Color errorSurface = Color(0xFFFFECEE);
  static const Color success = Color(0xFF2F855A);

  // 阴影（暖棕色调）
  static Color shadowWarm = const Color(0xFF0F172A).withValues(alpha: 0.08);
  static Color shadowMedium = const Color(0xFF0F172A).withValues(alpha: 0.12);
}

class AppTheme {
  AppTheme._();

  static ThemeData light() {
    const seedColor = Color(0xFF1F6F78);

    return ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(
        seedColor: seedColor,
        brightness: Brightness.light,
        primary: AppColors.primary,
        secondary: AppColors.primaryLight,
        surface: AppColors.surface,
        error: AppColors.error,
      ),
      scaffoldBackgroundColor: AppColors.background,
      fontFamily: 'Roboto',
      // App Bar
      appBarTheme: const AppBarTheme(
        backgroundColor: Colors.transparent,
        elevation: 0,
        scrolledUnderElevation: 0,
        iconTheme: IconThemeData(color: AppColors.textPrimary),
        titleTextStyle: TextStyle(
          fontFamily: 'Roboto',
          fontSize: 20,
          fontWeight: FontWeight.bold,
          color: AppColors.textPrimary,
        ),
      ),
      // Navigation Bar
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: AppColors.surface,
        indicatorColor: AppColors.primarySurface,
        iconTheme: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return const IconThemeData(color: AppColors.primary);
          }
          return IconThemeData(color: AppColors.textHint);
        }),
        labelTextStyle: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return const TextStyle(
              color: AppColors.primary,
              fontWeight: FontWeight.bold,
              fontSize: 12,
            );
          }
          return const TextStyle(
            color: AppColors.textHint,
            fontSize: 12,
          );
        }),
        elevation: 0,
        shadowColor: Colors.transparent,
        surfaceTintColor: Colors.transparent,
      ),
      // Card
      cardTheme: CardTheme(
        color: AppColors.surface,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
        ),
      ),
      // Input / TextField
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: Colors.transparent,
        hintStyle: const TextStyle(color: AppColors.textHint),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(20),
          borderSide: BorderSide.none,
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(20),
          borderSide: const BorderSide(color: AppColors.primary, width: 1.5),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(20),
          borderSide: BorderSide.none,
        ),
        prefixIconColor: AppColors.primary,
      ),
      // Elevated Button
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: AppColors.primary,
          foregroundColor: Colors.white,
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
          padding: const EdgeInsets.symmetric(vertical: 16),
          textStyle: const TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
      // Progress indicator
      progressIndicatorTheme: const ProgressIndicatorThemeData(
        color: AppColors.primary,
      ),
      // Divider
      dividerTheme: const DividerThemeData(
        color: AppColors.divider,
        thickness: 1,
        space: 1,
      ),
      // Text Theme
      textTheme: const TextTheme(
        displayLarge: TextStyle(color: AppColors.textPrimary, fontWeight: FontWeight.bold),
        displayMedium: TextStyle(color: AppColors.textPrimary, fontWeight: FontWeight.bold),
        headlineMedium: TextStyle(color: AppColors.textPrimary, fontWeight: FontWeight.bold),
        titleLarge: TextStyle(color: AppColors.textPrimary, fontWeight: FontWeight.bold),
        titleMedium: TextStyle(color: AppColors.textPrimary, fontWeight: FontWeight.w600),
        bodyLarge: TextStyle(color: AppColors.textPrimary),
        bodyMedium: TextStyle(color: AppColors.textSecondary),
        bodySmall: TextStyle(color: AppColors.textHint),
        labelLarge: TextStyle(color: AppColors.primary, fontWeight: FontWeight.w600),
      ),
      // Snack Bar
      snackBarTheme: SnackBarThemeData(
        backgroundColor: AppColors.textPrimary,
        contentTextStyle: const TextStyle(color: Colors.white),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        behavior: SnackBarBehavior.floating,
      ),
    );
  }
}
