import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../core/providers/app_state_provider.dart';
import '../theme/app_theme.dart';

class HistoryPage extends StatelessWidget {
  const HistoryPage({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppStateProvider>();

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text('历史记录'),
        centerTitle: false,
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 16),
            child: Text(
              '${state.sessions.length} 条',
              style: const TextStyle(
                color: AppColors.textHint,
                fontSize: 13,
              ),
            ),
          ),
        ],
      ),
      body: state.sessions.isEmpty
          ? _buildEmptyState()
          : ListView.builder(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
              itemCount: state.sessions.length,
              itemBuilder: (context, index) {
                final session = state.sessions[index];
                final dateStr = session['updated_at'] != null
                    ? _formatDate(session['updated_at'])
                    : '';
                final isActive = session['id'] == state.currentSessionId;

                return _SessionCard(
                  session: session,
                  dateStr: dateStr,
                  isActive: isActive,
                  onTap: () {
                    state.selectSession(session['id']);
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('已切换到选中对话，可返回助手页继续')),
                    );
                  },
                );
              },
            ),
    );
  }

  String _formatDate(dynamic timestamp) {
    final dt = DateTime.fromMillisecondsSinceEpoch((timestamp * 1000).toInt());
    final now = DateTime.now();
    final diff = now.difference(dt);
    if (diff.inDays == 0) return '今天 ${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
    if (diff.inDays == 1) return '昨天';
    if (diff.inDays < 7) return '${diff.inDays} 天前';
    return '${dt.month}月${dt.day}日';
  }

  Widget _buildEmptyState() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(
              color: AppColors.primarySurface,
              shape: BoxShape.circle,
            ),
            child: const Icon(
              Icons.menu_book_outlined,
              size: 48,
              color: AppColors.primary,
            ),
          ),
          const SizedBox(height: 20),
          const Text(
            '还没有对话记录',
            style: TextStyle(
              fontSize: 17,
              fontWeight: FontWeight.bold,
              color: AppColors.textPrimary,
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            '去和妮妮聊聊吧 🍳',
            style: TextStyle(fontSize: 14, color: AppColors.textHint),
          ),
        ],
      ),
    );
  }
}

class _SessionCard extends StatelessWidget {
  final Map<String, dynamic> session;
  final String dateStr;
  final bool isActive;
  final VoidCallback onTap;

  const _SessionCard({
    required this.session,
    required this.dateStr,
    required this.isActive,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(18),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 250),
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: isActive ? AppColors.primarySurface : AppColors.surface,
              borderRadius: BorderRadius.circular(18),
              border: Border.all(
                color: isActive
                    ? AppColors.primary.withValues(alpha: 0.4)
                    : AppColors.divider,
                width: isActive ? 1.5 : 1,
              ),
              boxShadow: [
                BoxShadow(
                  color: isActive
                      ? AppColors.primary.withValues(alpha: 0.08)
                      : AppColors.shadowWarm,
                  blurRadius: 10,
                  offset: const Offset(0, 4),
                ),
              ],
            ),
            child: Row(
              children: [
                // Leading icon
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    gradient: isActive
                        ? const LinearGradient(
                            colors: [AppColors.primary, AppColors.primaryLight],
                            begin: Alignment.topLeft,
                            end: Alignment.bottomRight,
                          )
                        : null,
                    color: isActive ? null : AppColors.primarySurface,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Icon(
                    Icons.chat_bubble_outline,
                    color: isActive ? Colors.white : AppColors.primary,
                    size: 20,
                  ),
                ),
                const SizedBox(width: 14),
                // Content
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        session['title'] ?? '新对话',
                        style: TextStyle(
                          fontWeight: FontWeight.bold,
                          fontSize: 15,
                          color: isActive ? AppColors.primary : AppColors.textPrimary,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: 4),
                      Text(
                        dateStr,
                        style: const TextStyle(
                          fontSize: 12,
                          color: AppColors.textHint,
                        ),
                      ),
                    ],
                  ),
                ),
                // Trailing
                if (isActive)
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: AppColors.primary,
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: const Text(
                      '当前',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 11,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  )
                else
                  const Icon(Icons.chevron_right, color: AppColors.textHint, size: 20),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
