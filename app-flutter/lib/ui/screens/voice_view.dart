import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../core/providers/app_state_provider.dart';
import '../theme/app_theme.dart';

class VoiceView extends StatefulWidget {
  const VoiceView({super.key});

  @override
  State<VoiceView> createState() => _VoiceViewState();
}

class _VoiceViewState extends State<VoiceView> with SingleTickerProviderStateMixin {
  late AnimationController _pulseController;
  final List<_MiniMessage> _messages = [];
  String _lastAsrText = '';
  String _lastLlmText = '';

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1600),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _pulseController.dispose();
    super.dispose();
  }

  void _maybeAppendMessage(String text, bool isUser) {
    if (text.isEmpty) return;
    if (isUser) {
      if (text == _lastAsrText) return;
      _lastAsrText = text;
    } else {
      if (text == _lastLlmText) return;
      _lastLlmText = text;
    }
    _messages.add(_MiniMessage(text: text, isUser: isUser, id: DateTime.now().microsecondsSinceEpoch));
    while (_messages.length > 3) {
      _messages.removeAt(0);
    }
  }

  /// 根据当前小时返回温馨问候语
  String _getGreeting() {
    final hour = DateTime.now().hour;
    if (hour < 6) return '夜深了，大厨';
    if (hour < 11) return '早安，大厨 🌤️';
    if (hour < 14) return '午好，大厨 ☀️';
    if (hour < 18) return '下午好，大厨 🍵';
    return '晚上好，大厨 🌙';
  }

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppStateProvider>();
    final bool isActive = state.connectionState == VoiceConnectionState.connected;
    final bool isConnecting = state.connectionState == VoiceConnectionState.connecting;

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final beforeCount = _messages.length;
      _maybeAppendMessage(state.asrText, true);
      _maybeAppendMessage(state.llmText, false);
      if (_messages.length != beforeCount) {
        setState(() {});
      }
    });

    return Stack(
      children: [
        Container(
          decoration: const BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [
                Color(0xFFF6F8FA),
                Color(0xFFEAF3F1),
              ],
            ),
          ),
        ),
        Positioned(
          top: -60,
          left: -30,
          child: _GlowOrb(color: AppColors.primary.withValues(alpha: 0.12), size: 220),
        ),
        Positioned(
          bottom: -90,
          right: -40,
          child: _GlowOrb(color: AppColors.primaryLight.withValues(alpha: 0.14), size: 260),
        ),
        SafeArea(
          child: Column(
            children: [
              // ── 顶部问候区 ──────────────────────────
              Padding(
                padding: const EdgeInsets.only(top: 24, left: 24, right: 24),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            '厨房助手',
                            style: TextStyle(
                              color: AppColors.textHint,
                              fontSize: 12,
                              letterSpacing: 1.2,
                            ),
                          ),
                          const SizedBox(height: 6),
                          Text(
                            _getGreeting(),
                            style: const TextStyle(
                              color: AppColors.textPrimary,
                              fontSize: 26,
                              fontWeight: FontWeight.w700,
                              height: 1.2,
                            ),
                          ),
                        ],
                      ),
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                      decoration: BoxDecoration(
                        color: isActive ? AppColors.primarySurface : AppColors.surfaceVariant,
                        borderRadius: BorderRadius.circular(20),
                        border: Border.all(color: AppColors.divider),
                      ),
                      child: Row(
                        children: [
                          Icon(
                            isActive
                                ? Icons.wifi_tethering_rounded
                                : isConnecting
                                    ? Icons.wifi_rounded
                                    : Icons.wifi_tethering_off_rounded,
                            size: 16,
                            color: isActive ? AppColors.primary : AppColors.textHint,
                          ),
                          const SizedBox(width: 6),
                          Text(
                            isActive ? '在线' : isConnecting ? '连接中' : '未连接',
                            style: TextStyle(
                              color: isActive ? AppColors.primary : AppColors.textHint,
                              fontSize: 12,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              Padding(
                padding: const EdgeInsets.only(left: 24, right: 24, top: 12),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.85),
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(color: AppColors.divider),
                  ),
                  child: Row(
                    children: [
                      Icon(
                        isActive ? Icons.mic_rounded : Icons.mic_none_rounded,
                        size: 18,
                        color: isActive ? AppColors.primary : AppColors.textHint,
                      ),
                      const SizedBox(width: 8),
                      Text(
                        isActive
                            ? '正在聆听，可点击停止'
                            : isConnecting
                                ? '正在连接，请稍候'
                                : '点击开始语音对话',
                        style: TextStyle(
                          color: isActive ? AppColors.textPrimary : AppColors.textSecondary,
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                ),
              ),

              // ── 中央麦克风按钮 ───────────────────────
              Expanded(
                child: Center(
                  child: GestureDetector(
                    onTap: () async {
                      if (isActive) {
                        await context.read<AppStateProvider>().stopVoiceChat();
                      } else {
                        await context.read<AppStateProvider>().startVoiceChat();
                      }
                    },
                    child: AnimatedBuilder(
                      animation: _pulseController,
                      builder: (context, child) {
                        final rotation = _pulseController.value * 2 * 3.14159;
                        return Stack(
                          alignment: Alignment.center,
                          children: [
                            if (isActive) ...[
                              Opacity(
                                opacity: 0.08 + _pulseController.value * 0.05,
                                child: Container(
                                  width: 250 + _pulseController.value * 70,
                                  height: 250 + _pulseController.value * 70,
                                  decoration: BoxDecoration(
                                    shape: BoxShape.circle,
                                    color: AppColors.primary,
                                  ),
                                ),
                              ),
                              Opacity(
                                opacity: 0.10 + _pulseController.value * 0.06,
                                child: Container(
                                  width: 180 + _pulseController.value * 45,
                                  height: 180 + _pulseController.value * 45,
                                  decoration: BoxDecoration(
                                    shape: BoxShape.circle,
                                    color: AppColors.primaryLight,
                                  ),
                                ),
                              ),
                            ],
                            Transform.rotate(
                              angle: rotation,
                              child: Container(
                                width: 196,
                                height: 196,
                                decoration: BoxDecoration(
                                  shape: BoxShape.circle,
                                  gradient: const SweepGradient(
                                    colors: [
                                      Color(0x00000000),
                                      Color(0x661F6F78),
                                      Color(0x00000000),
                                      Color(0x664FB3B0),
                                      Color(0x00000000),
                                    ],
                                  ),
                                ),
                              ),
                            ),
                            AnimatedContainer(
                              duration: const Duration(milliseconds: 320),
                              curve: Curves.easeInOut,
                              width: isActive ? 156 : 146,
                              height: isActive ? 156 : 146,
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                gradient: isActive
                                    ? const LinearGradient(
                                        colors: [AppColors.primary, AppColors.primaryLight],
                                        begin: Alignment.topLeft,
                                        end: Alignment.bottomRight,
                                      )
                                    : const LinearGradient(
                                        colors: [Colors.white, Color(0xFFE9EEF2)],
                                        begin: Alignment.topLeft,
                                        end: Alignment.bottomRight,
                                      ),
                                boxShadow: [
                                  BoxShadow(
                                    color: AppColors.shadowMedium,
                                    blurRadius: isActive ? 26 : 18,
                                    offset: const Offset(0, 10),
                                  ),
                                ],
                                border: isActive
                                    ? null
                                    : Border.all(
                                        color: AppColors.divider,
                                        width: 1.2,
                                      ),
                              ),
                              child: Stack(
                                alignment: Alignment.center,
                                children: [
                                  Container(
                                    width: isActive ? 104 : 96,
                                    height: isActive ? 104 : 96,
                                    decoration: BoxDecoration(
                                      shape: BoxShape.circle,
                                      color: Colors.white.withValues(alpha: isActive ? 0.12 : 0.6),
                                    ),
                                  ),
                                  Icon(
                                    isActive ? Icons.mic : Icons.mic_none_outlined,
                                    color: isActive ? Colors.white : AppColors.textSecondary,
                                    size: 54,
                                  ),
                                ],
                              ),
                            ),
                          ],
                        );
                      },
                    ),
                  ),
                ),
              ),

              // ── 底部对话区 ───────────────────────────
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 20),
                child: Column(
                  children: [
                    AnimatedSwitcher(
                      duration: const Duration(milliseconds: 300),
                      child: Text(
                        isActive ? '轻触停止对话' : '轻触开始说话',
                        key: ValueKey(isActive),
                        style: TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                          color: isActive ? AppColors.primary : AppColors.textSecondary,
                        ),
                      ),
                    ),
                    const SizedBox(height: 10),
                    SizedBox(
                      height: 120,
                      child: _FloatingTextStack(messages: _messages),
                    ),
                    const SizedBox(height: 8),
                    AnimatedOpacity(
                      opacity: (isActive && state.isAIPlayback) ? 1.0 : 0.0,
                      duration: const Duration(milliseconds: 300),
                      child: IgnorePointer(
                        ignoring: !(isActive && state.isAIPlayback),
                        child: TextButton.icon(
                          onPressed: () {
                            context.read<AppStateProvider>().interruptAI();
                          },
                          icon: const Icon(Icons.stop_circle_outlined, color: AppColors.error),
                          label: const Text('打断 AI 说话', style: TextStyle(color: AppColors.error)),
                          style: TextButton.styleFrom(
                            backgroundColor: AppColors.errorSurface,
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(20),
                            ),
                            padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 10),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _MiniMessage {
  final String text;
  final bool isUser;
  final int id;

  const _MiniMessage({required this.text, required this.isUser, required this.id});
}

class _FloatingTextStack extends StatelessWidget {
  final List<_MiniMessage> messages;

  const _FloatingTextStack({required this.messages});

  @override
  Widget build(BuildContext context) {
    final visible = messages.length <= 3 ? messages : messages.sublist(messages.length - 3);
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 260),
      transitionBuilder: (child, animation) {
        final slide = Tween<Offset>(
          begin: const Offset(0, 0.12),
          end: Offset.zero,
        ).animate(CurvedAnimation(parent: animation, curve: Curves.easeOut));
        return FadeTransition(
          opacity: animation,
          child: SlideTransition(position: slide, child: child),
        );
      },
      child: Column(
        key: ValueKey(visible.isEmpty ? 0 : visible.last.id),
        mainAxisAlignment: MainAxisAlignment.end,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: List.generate(visible.length, (index) {
          final msg = visible[index];
          final age = visible.length - 1 - index;
          final double opacity = age == 0 ? 0.92 : age == 1 ? 0.55 : 0.28;
          final double scale = age == 0 ? 1.0 : age == 1 ? 0.92 : 0.86;
          return AnimatedOpacity(
            opacity: opacity,
            duration: const Duration(milliseconds: 280),
            child: AnimatedScale(
              scale: scale,
              duration: const Duration(milliseconds: 280),
              alignment: Alignment.topLeft,
              child: Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Text(
                  msg.text,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: msg.isUser ? AppColors.textSecondary : AppColors.textPrimary,
                    fontSize: 14,
                    height: 1.45,
                    shadows: [
                      Shadow(
                        color: AppColors.primary.withValues(alpha: 0.12),
                        blurRadius: 6,
                        offset: const Offset(0, 2),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          );
        }),
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
