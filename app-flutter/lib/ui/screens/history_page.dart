import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../core/providers/app_state_provider.dart';

class HistoryPage extends StatelessWidget {
  const HistoryPage({super.key});

  @override
  Widget build(BuildContext context) {
    final state = context.watch<AppStateProvider>();
    
    return Scaffold(
      backgroundColor: const Color(0xFFF6F8FD),
      appBar: AppBar(
        title: const Text('历史记录', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 20)),
        backgroundColor: Colors.transparent,
        elevation: 0,
        centerTitle: false,
      ),
      body: state.sessions.isEmpty
          ? const Center(child: Text('暂无历史对话', style: TextStyle(color: Colors.black54)))
          : ListView.builder(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              itemCount: state.sessions.length,
              itemBuilder: (context, index) {
                final session = state.sessions[index];
                final dateStr = session['updated_at'] != null 
                  ? DateTime.fromMillisecondsSinceEpoch((session['updated_at'] * 1000).toInt()).toString().split('.')[0]
                  : '';
                  
                final isActive = session['id'] == state.currentSessionId;
                  
                return Card(
                  elevation: 0,
                  margin: const EdgeInsets.only(bottom: 12),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(16), 
                    side: BorderSide(color: isActive ? Colors.blueAccent : Colors.grey.withValues(alpha: 0.1), width: isActive ? 2 : 1)
                  ),
                  color: isActive ? Colors.blue.shade50 : Colors.white,
                  child: ListTile(
                    contentPadding: const EdgeInsets.all(16),
                    leading: Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(color: isActive ? Colors.blueAccent : Colors.blue.shade50, borderRadius: BorderRadius.circular(12)),
                      child: Icon(Icons.chat_bubble_outline, color: isActive ? Colors.white : Colors.blueAccent),
                    ),
                    title: Text(session['title'] ?? '新对话', style: const TextStyle(fontWeight: FontWeight.bold)),
                    subtitle: Padding(
                      padding: const EdgeInsets.only(top: 8.0),
                      child: Text(dateStr, style: TextStyle(color: Colors.grey.shade500, fontSize: 12)),
                    ),
                    onTap: () {
                      state.selectSession(session['id']);
                      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('已切换到选中对话，可返回首页继续')));
                    },
                  ),
                );
              },
            ),
    );
  }
}
