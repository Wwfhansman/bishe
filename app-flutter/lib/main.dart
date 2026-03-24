import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'core/providers/app_state_provider.dart';
import 'ui/screens/login_page.dart';
import 'ui/screens/home_page.dart';
import 'ui/theme/app_theme.dart';

void main() {
  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => AppStateProvider()),
      ],
      child: const NiniApp(),
    ),
  );
}

class NiniApp extends StatelessWidget {
  const NiniApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '厨房助理 妮妮',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      home: Consumer<AppStateProvider>(
        builder: (context, state, child) {
          return state.isAuthenticated ? const HomePage() : const LoginPage();
        },
      ),
    );
  }
}
