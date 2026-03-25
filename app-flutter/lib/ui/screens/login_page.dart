import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../core/providers/app_state_provider.dart';
import '../theme/app_theme.dart';

class LoginPage extends StatefulWidget {
  const LoginPage({super.key});

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> with SingleTickerProviderStateMixin {
  final TextEditingController _usernameController = TextEditingController();
  final TextEditingController _passwordController = TextEditingController();
  bool _isLoading = false;
  late AnimationController _fadeController;
  late Animation<double> _fadeAnim;

  @override
  void initState() {
    super.initState();
    _fadeController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    )..forward();
    _fadeAnim = CurvedAnimation(parent: _fadeController, curve: Curves.easeOut);
  }

  Future<void> _submit(bool isLogin) async {
    final state = context.read<AppStateProvider>();
    setState(() => _isLoading = true);

    final username = _usernameController.text.trim();
    final password = _passwordController.text;

    if (username.isEmpty || password.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('请输入用户名和密码')));
      setState(() => _isLoading = false);
      return;
    }

    bool success;
    if (isLogin) {
      success = await state.login(username, password);
    } else {
      success = await state.register(username, password);
    }

    if (!mounted) return;
    setState(() => _isLoading = false);

    if (!success) {
      final detail = state.lastErrorMessage ?? 'unknown_error';
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('操作失败：$detail')),
      );
    }
  }

  @override
  void dispose() {
    _usernameController.dispose();
    _passwordController.dispose();
    _fadeController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Stack(
        children: [
          Container(
            decoration: const BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [
                  Color(0xFFF3F6F8),
                  Color(0xFFE9F3F1),
                ],
              ),
            ),
          ),
          Positioned(
            top: -80,
            left: -40,
            child: _GlowOrb(color: AppColors.primary.withValues(alpha: 0.15), size: 220),
          ),
          Positioned(
            bottom: -120,
            right: -60,
            child: _GlowOrb(color: AppColors.primaryLight.withValues(alpha: 0.18), size: 260),
          ),
          SafeArea(
            child: Center(
              child: FadeTransition(
                opacity: _fadeAnim,
                child: SingleChildScrollView(
                  padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 40),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      // Logo
                      Container(
                        padding: const EdgeInsets.all(20),
                        decoration: BoxDecoration(
                          color: Colors.white,
                          shape: BoxShape.circle,
                          boxShadow: [
                            BoxShadow(
                              color: AppColors.primary.withValues(alpha: 0.18),
                              blurRadius: 32,
                              offset: const Offset(0, 14),
                            ),
                            BoxShadow(
                              color: AppColors.primary.withValues(alpha: 0.06),
                              blurRadius: 8,
                              offset: const Offset(0, 4),
                            ),
                          ],
                        ),
                        child: const Icon(Icons.restaurant_rounded, size: 58, color: AppColors.primary),
                      ),
                      const SizedBox(height: 22),
                      const Text(
                        '厨房助理 妮妮',
                        style: TextStyle(
                          fontSize: 28,
                          fontWeight: FontWeight.w700,
                          color: AppColors.textPrimary,
                        ),
                      ),
                      const SizedBox(height: 8),
                      const Text(
                        '语音对话，实时掌握火候',
                        style: TextStyle(fontSize: 14, color: AppColors.textSecondary, height: 1.5),
                      ),
                      const SizedBox(height: 36),

                      // Form Card
                      Container(
                        padding: const EdgeInsets.symmetric(vertical: 6),
                        decoration: BoxDecoration(
                          color: Colors.white.withValues(alpha: 0.9),
                          borderRadius: BorderRadius.circular(22),
                          border: Border.all(color: AppColors.divider),
                          boxShadow: [
                            BoxShadow(
                              color: AppColors.shadowWarm,
                              blurRadius: 18,
                              offset: const Offset(0, 8),
                            ),
                          ],
                        ),
                        child: Column(
                          children: [
                            TextField(
                              controller: _usernameController,
                              style: const TextStyle(color: AppColors.textPrimary),
                              decoration: const InputDecoration(
                                hintText: '用户名',
                                prefixIcon: Icon(Icons.person_outline),
                              ),
                            ),
                            const Divider(height: 1, color: AppColors.divider, indent: 18, endIndent: 18),
                            TextField(
                              controller: _passwordController,
                              obscureText: true,
                              style: const TextStyle(color: AppColors.textPrimary),
                              decoration: const InputDecoration(
                                hintText: '密码',
                                prefixIcon: Icon(Icons.lock_outline),
                              ),
                              onSubmitted: (_) => _submit(true),
                            ),
                          ],
                        ),
                      ),

                      const SizedBox(height: 24),

                      // Error message
                      Consumer<AppStateProvider>(
                        builder: (_, state, __) {
                          final detail = state.lastErrorMessage;
                          if (detail == null || detail.isEmpty) return const SizedBox.shrink();
                          return Container(
                            width: double.infinity,
                            margin: const EdgeInsets.only(bottom: 16),
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: AppColors.errorSurface,
                              borderRadius: BorderRadius.circular(12),
                              border: Border.all(color: AppColors.error.withValues(alpha: 0.2)),
                            ),
                            child: Text(
                              '当前错误：$detail',
                              style: const TextStyle(fontSize: 12, color: AppColors.error),
                            ),
                          );
                        },
                      ),

                      // Actions
                      if (_isLoading)
                        const Padding(
                          padding: EdgeInsets.all(8.0),
                          child: CircularProgressIndicator(),
                        )
                      else
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            Container(
                              decoration: BoxDecoration(
                                gradient: const LinearGradient(
                                  colors: [AppColors.primary, AppColors.primaryLight],
                                  begin: Alignment.centerLeft,
                                  end: Alignment.centerRight,
                                ),
                                borderRadius: BorderRadius.circular(16),
                                boxShadow: [
                                  BoxShadow(
                                    color: AppColors.primary.withValues(alpha: 0.28),
                                    blurRadius: 16,
                                    offset: const Offset(0, 8),
                                  ),
                                ],
                              ),
                              child: ElevatedButton(
                                onPressed: () => _submit(true),
                                style: ElevatedButton.styleFrom(
                                  backgroundColor: Colors.transparent,
                                  shadowColor: Colors.transparent,
                                  foregroundColor: Colors.white,
                                ),
                                child: const Text('登 录'),
                              ),
                            ),
                            const SizedBox(height: 12),
                            TextButton(
                              onPressed: () => _submit(false),
                              style: TextButton.styleFrom(
                                foregroundColor: AppColors.textSecondary,
                              ),
                              child: const Text('新用户？点击注册', style: TextStyle(fontSize: 14)),
                            ),
                          ],
                        ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _GlowOrb extends StatelessWidget {
  final Color color;
  final double size;

  const _GlowOrb({required this.color, required this.size});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: color,
        boxShadow: [
          BoxShadow(
            color: color,
            blurRadius: 60,
            spreadRadius: 6,
          ),
        ],
      ),
    );
  }
}
