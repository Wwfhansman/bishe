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

    return Container(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            Color(0xFFFFF3E0), // 顶部暖杏
            Color(0xFFFFF8F0), // 底部奶油白
          ],
        ),
      ),
      child: SafeArea(
        child: Column(
          children: [
            // ── 顶部问候区 ──────────────────────────
            Padding(
              padding: const EdgeInsets.only(top: 28, left: 28, right: 28),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          '厨房助手 妮妮',
                          style: TextStyle(
                            color: AppColors.textHint,
                            fontSize: 13,
                            letterSpacing: 1.2,
                          ),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          _getGreeting(),
                          style: const TextStyle(
                            color: AppColors.textPrimary,
                            fontSize: 26,
                            fontWeight: FontWeight.bold,
                            height: 1.2,
                          ),
                        ),
                      ],
                    ),
                  ),
                  // 状态指示小图标
                  Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: isActive
                          ? AppColors.primarySurface
                          : const Color(0xFFF5EFEB),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Icon(
                      isActive ? Icons.graphic_eq : Icons.music_note_outlined,
                      size: 20,
                      color: isActive ? AppColors.primary : AppColors.textHint,
                    ),
                  ),
                ],
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
                      return Stack(
                        alignment: Alignment.center,
                        children: [
                          if (isActive) ...[
                            // 外层光晕 1
                            Opacity(
                              opacity: 0.06 + _pulseController.value * 0.04,
                              child: Container(
                                width: 240 + _pulseController.value * 70,
                                height: 240 + _pulseController.value * 70,
                                decoration: BoxDecoration(
                                  shape: BoxShape.circle,
                                  color: AppColors.primary,
                                ),
                              ),
                            ),
                            // 外层光晕 2
                            Opacity(
                              opacity: 0.08 + _pulseController.value * 0.06,
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

                          // 主按钮容器
                          AnimatedContainer(
                            duration: const Duration(milliseconds: 400),
                            curve: Curves.easeInOut,
                            width: isActive ? 148 : 138,
                            height: isActive ? 148 : 138,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              gradient: isActive
                                  ? const LinearGradient(
                                      colors: [AppColors.primary, AppColors.primaryLight],
                                      begin: Alignment.topLeft,
                                      end: Alignment.bottomRight,
                                    )
                                  : const LinearGradient(
                                      colors: [Color(0xFFF5EFEB), Color(0xFFEDE0D8)],
                                      begin: Alignment.topLeft,
                                      end: Alignment.bottomRight,
                                    ),
                              boxShadow: isActive
                                  ? [
                                      BoxShadow(
                                        color: AppColors.primary.withValues(alpha: 0.35),
                                        blurRadius: 28,
                                        offset: const Offset(0, 12),
                                      ),
                                      BoxShadow(
                                        color: AppColors.primaryLight.withValues(alpha: 0.15),
                                        blurRadius: 8,
                                        offset: const Offset(0, 4),
                                      ),
                                    ]
                                  : [
                                      BoxShadow(
                                        color: AppColors.shadowMedium,
                                        blurRadius: 20,
                                        offset: const Offset(0, 8),
                                      ),
                                    ],
                              border: isActive
                                  ? null
                                  : Border.all(
                                      color: const Color(0xFFD4B8AE),
                                      width: 1.5,
                                    ),
                            ),
                            child: Icon(
                              isActive ? Icons.mic : Icons.mic_none_outlined,
                              color: isActive ? Colors.white : AppColors.textSecondary,
                              size: 50,
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
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 28),
              child: Column(
                children: [
                  // 操作提示
                  AnimatedSwitcher(
                    duration: const Duration(milliseconds: 300),
                    child: Text(
                      isActive ? '轻触停止对话' : '轻触开始说话',
                      key: ValueKey(isActive),
                      style: TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                        color: isActive ? AppColors.primary : AppColors.textSecondary,
                        letterSpacing: 0.5,
                      ),
                    ),
                  ),
                  const SizedBox(height: 20),

                  // 对话气泡区：固定高度，防止布局抖动
                  SizedBox(
                    height: 140,
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.end,
                      children: [
                        // ASR 气泡（用户语音转文字）
                        _AnimatedMessageBubble(
                          text: state.asrText,
                          isUser: true,
                        ),
                        if (state.asrText.isNotEmpty && state.llmText.isNotEmpty)
                          const SizedBox(height: 8),
                        // LLM 气泡（AI 回复）
                        _AnimatedMessageBubble(
                          text: state.llmText,
                          isUser: false,
                        ),
                      ],
                    ),
                  ),

                  // 打断按钮
                  const SizedBox(height: 12),
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
                          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
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
    );
  }
}

/// 带滑入+淡出动效的消息气泡
class _AnimatedMessageBubble extends StatelessWidget {
  final String text;
  final bool isUser;

  const _AnimatedMessageBubble({required this.text, required this.isUser});

  @override
  Widget build(BuildContext context) {
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 400),
      reverseDuration: const Duration(milliseconds: 250),
      transitionBuilder: (child, animation) {
        // 滑入：从下方 dy=0.25 滑入 + fade in
        final slideAnim = Tween<Offset>(
          begin: const Offset(0, 0.25),
          end: Offset.zero,
        ).animate(CurvedAnimation(parent: animation, curve: Curves.easeOut));

        return FadeTransition(
          opacity: animation,
          child: SlideTransition(position: slideAnim, child: child),
        );
      },
      child: text.isEmpty
          ? const SizedBox.shrink()
          : Container(
              key: ValueKey('${isUser}_$text'),
              width: double.infinity,
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              decoration: BoxDecoration(
                color: isUser ? Colors.white : AppColors.primarySurface,
                borderRadius: BorderRadius.circular(14),
                border: isUser
                    ? Border(
                        left: BorderSide(
                          color: AppColors.textHint.withValues(alpha: 0.5),
                          width: 3,
                        ),
                      )
                    : Border(
                        left: BorderSide(
                          color: AppColors.primary.withValues(alpha: 0.6),
                          width: 3,
                        ),
                      ),
                boxShadow: [
                  BoxShadow(
                    color: AppColors.shadowWarm,
                    blurRadius: 8,
                    offset: const Offset(0, 3),
                  ),
                ],
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    isUser ? '🗣 ' : '🍴 ',
                    style: const TextStyle(fontSize: 15),
                  ),
                  const SizedBox(width: 4),
                  Expanded(
                    child: Text(
                      text,
                      style: TextStyle(
                        fontSize: 14,
                        height: 1.5,
                        color: isUser ? AppColors.textSecondary : AppColors.textPrimary,
                        fontWeight: isUser ? FontWeight.normal : FontWeight.w500,
                      ),
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ),
            ),
    );
  }
}
